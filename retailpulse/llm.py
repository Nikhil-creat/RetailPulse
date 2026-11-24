"""Optional LLM client. Everything works without it (deterministic fallbacks).

Set ANTHROPIC_API_KEY to let the RAG layer write fluent answers and the agent plan with an LLM.
The key is read from the environment only and is never logged or written to disk.
"""
from __future__ import annotations

import os

import requests

API_URL = "https://api.anthropic.com/v1/messages"


class LLMClient:
    def __init__(self, api_key: str | None = None, model: str | None = None, timeout: float = 20.0):
        self._api_key = api_key
        self.model = model or os.getenv("RP_LLM_MODEL", "claude-sonnet-5-5")
        self.timeout = timeout

    @classmethod
    def from_env(cls) -> "LLMClient":
        return cls(api_key=os.getenv("ANTHROPIC_API_KEY"))

    @property
    def enabled(self) -> bool:
        return bool(self._api_key)

    def complete(self, system: str, user: str, max_tokens: int = 500) -> str | None:
        """Returns text, or None on any failure (callers must have a fallback)."""
        if not self.enabled:
            return None
        try:
            r = requests.post(
                API_URL, timeout=self.timeout,
                headers={"x-api-key": self._api_key, "anthropic-version": "2023-06-01",
                         "content-type": "application/json"},
                json={"model": self.model, "max_tokens": max_tokens, "system": system,
                      "messages": [{"role": "user", "content": user}]},
            )
            r.raise_for_status()
            return r.json()["content"][0]["text"]
        except Exception:  # network, auth, schema: never leak details, just fall back
            return None
