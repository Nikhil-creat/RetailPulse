import os
import time
from typing import Any
import httpx

class AutoModelRouter:
    """Dynamically discovers active chat/multimodal models from Groq & Gemini."""

    def __init__(self, ttl_seconds: int = 900) -> None:
        self.groq_key = os.getenv("GROQ_API_KEY", "").strip()
        self.gemini_key = os.getenv("GEMINI_API_KEY", "").strip()
        self.ttl = ttl_seconds
        self._cache: dict[str, Any] = {"ts": 0.0, "groq": [], "gemini": []}

    def discover_models(self, force: bool = False) -> dict[str, list[str]]:
        now = time.time()
        if not force and (now - self._cache["ts"]) < self.ttl:
            return {"groq": self._cache["groq"], "gemini": self._cache["gemini"]}

        groq_models: list[str] = []
        if self.groq_key:
            try:
                r = httpx.get(
                    "https://api.groq.com/openai/v1/models",
                    headers={"Authorization": f"Bearer {self.groq_key}"},
                    timeout=8.0,
                )
                r.raise_for_status()
                ids = [m.get("id", "") for m in r.json().get("data", [])]
                groq_models = [
                    mid for mid in ids
                    if mid and not any(s in mid.lower() for s in ("guard", "whisper", "orpheus", "embed", "tts"))
                ]
            except Exception:
                groq_models = []

        gemini_models: list[str] = []
        if self.gemini_key:
            try:
                r = httpx.get(
                    "https://generativelanguage.googleapis.com/v1beta/models",
                    headers={"x-goog-api-key": self.gemini_key},
                    timeout=8.0,
                )
                r.raise_for_status()
                for m in r.json().get("models", []):
                    methods = m.get("supportedGenerationMethods", [])
                    name = m.get("name", "").removeprefix("models/")
                    if name and "generateContent" in methods:
                        gemini_models.append(name)
            except Exception:
                gemini_models = []

        self._cache = {"ts": now, "groq": groq_models, "gemini": gemini_models}
        return {"groq": groq_models, "gemini": gemini_models}

    def pick_model(self, prefer: str = "groq") -> dict[str, str]:
        found = self.discover_models()
        order = [("groq", found["groq"]), ("gemini", found["gemini"])]
        if prefer == "gemini":
            order.reverse()
        for provider, models in order:
            if models:
                ranked = sorted(
                    models,
                    key=lambda x: (0 if any(k in x.lower() for k in ("flash", "versatile", "instant")) else 1, x),
                )
                return {"provider": provider, "model": ranked[0], "mode": "live"}
        return {"provider": "local", "model": "deterministic-sql-fallback", "mode": "offline"}
