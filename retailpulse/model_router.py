"""Discover which hosted chat models are currently available (Groq, Gemini) and pick one.

Optional and offline-safe: with no API keys, or when a provider is unreachable, ``pick_model`` returns the
local deterministic fallback and the rest of RetailPulse keeps working (every answer is already produced
without an LLM; the LLM is only allowed to reword grounded answers).

Security notes
- Keys are read from the environment only, must look like a token (no whitespace/newlines, so they cannot
  inject headers), are sent in headers over HTTPS, and never appear in ``repr``, ``status()`` or logs.
- Only the two hard-coded HTTPS endpoints are contacted. Responses are size-capped.
- Provider errors are recorded by exception class name only.
Limitation: the discovery code is unit-tested with a fake fetcher; it has not been run against the live
Groq/Gemini APIs here (no keys in the build environment).
"""
from __future__ import annotations

import json
import os
import re
import time
import urllib.request
from typing import Any, Callable

GROQ_URL = "https://api.groq.com/openai/v1/models"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models"
_KEY_OK = re.compile(r"^[A-Za-z0-9_\-.]{8,256}$")
_SKIP = ("guard", "whisper", "orpheus", "embed", "tts", "aqa", "imagen", "veo")
_PREFER = ("flash", "versatile", "instant")
MAX_BYTES = 2_000_000

Fetch = Callable[[str, dict, float], Any]


def _urllib_fetch(url: str, headers: dict, timeout: float) -> Any:
    if not url.startswith("https://"):
        raise ValueError("https only")
    req = urllib.request.Request(url, headers={**headers, "Accept": "application/json", "User-Agent": "retailpulse"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310 (scheme checked above)
        return json.loads(resp.read(MAX_BYTES))


def _clean_key(raw: str | None) -> str:
    raw = (raw or "").strip()
    return raw if _KEY_OK.match(raw) else ""


class AutoModelRouter:
    def __init__(self, ttl_seconds: int = 900, fetch: Fetch | None = None, env: dict | None = None,
                 clock: Callable[[], float] = time.time, timeout: float = 8.0):
        env = os.environ if env is None else env
        self._groq_key = _clean_key(env.get("GROQ_API_KEY"))
        self._gemini_key = _clean_key(env.get("GEMINI_API_KEY"))
        self.ttl, self.timeout, self._clock = ttl_seconds, timeout, clock
        self._fetch: Fetch = fetch or _urllib_fetch
        self._cache: dict[str, Any] = {"ts": None, "groq": [], "gemini": []}
        self.errors: dict[str, str] = {}

    def __repr__(self) -> str:  # never include key material
        return f"AutoModelRouter(groq={bool(self._groq_key)}, gemini={bool(self._gemini_key)}, ttl={self.ttl})"

    def status(self) -> dict:
        return {"groq_configured": bool(self._groq_key), "gemini_configured": bool(self._gemini_key),
                "errors": dict(self.errors), "cached_at": self._cache["ts"], "ttl_seconds": self.ttl}

    def _groq(self) -> list[str]:
        data = self._fetch(GROQ_URL, {"Authorization": f"Bearer {self._groq_key}"}, self.timeout)
        ids = [str(m.get("id", "")) for m in data.get("data", []) if isinstance(m, dict)]
        return [i for i in ids if i and not any(s in i.lower() for s in _SKIP)]

    def _gemini(self) -> list[str]:
        data = self._fetch(GEMINI_URL, {"x-goog-api-key": self._gemini_key}, self.timeout)
        out = []
        for m in data.get("models", []):
            name = str(m.get("name", "")).removeprefix("models/")
            if name and "generateContent" in m.get("supportedGenerationMethods", []) \
                    and not any(s in name.lower() for s in _SKIP):
                out.append(name)
        return out

    def discover_models(self, force: bool = False) -> dict[str, list[str]]:
        now = self._clock()
        ts = self._cache["ts"]
        if not force and ts is not None and now - ts < self.ttl:
            return {"groq": list(self._cache["groq"]), "gemini": list(self._cache["gemini"])}
        found: dict[str, list[str]] = {"groq": [], "gemini": []}
        self.errors = {}
        for provider, key, fn in (("groq", self._groq_key, self._groq), ("gemini", self._gemini_key, self._gemini)):
            if not key:
                continue
            try:
                found[provider] = fn()
            except Exception as e:  # noqa: BLE001 (any provider failure must degrade to offline)
                self.errors[provider] = type(e).__name__
        self._cache = {"ts": now, **found}
        return {k: list(v) for k, v in found.items()}

    def pick_model(self, prefer: str = "groq") -> dict[str, str]:
        found = self.discover_models()
        order = [("groq", found["groq"]), ("gemini", found["gemini"])]
        if prefer == "gemini":
            order.reverse()
        for provider, models in order:
            if models:
                best = sorted(models, key=lambda m: (0 if any(k in m.lower() for k in _PREFER) else 1, m))[0]
                return {"provider": provider, "model": best, "mode": "live"}
        return {"provider": "local", "model": "deterministic-sql-fallback", "mode": "offline"}
