"""Tiny in-process ASGI test client (no httpx needed)."""
from __future__ import annotations

import asyncio
import json
from urllib.parse import urlsplit


class Resp:
    def __init__(self, status: int, headers: dict, body: bytes):
        self.status, self.headers, self.body = status, headers, body

    def json(self):
        return json.loads(self.body)


def request(app, method: str, url: str, headers: dict | None = None, body: bytes = b"",
            client=("203.0.113.9", 5000)) -> Resp:
    parts = urlsplit(url)
    hdrs = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if body and not any(k == b"content-length" for k, _ in hdrs):
        hdrs.append((b"content-length", str(len(body)).encode()))
    scope = {"type": "http", "asgi": {"version": "3.0"}, "http_version": "1.1", "method": method,
             "scheme": "http", "path": parts.path, "raw_path": parts.path.encode(),
             "query_string": parts.query.encode(), "headers": hdrs, "client": client,
             "server": ("testserver", 80)}
    sent, out = False, {"status": 0, "headers": {}, "body": b""}

    async def receive():
        nonlocal sent
        if not sent:
            sent = True
            return {"type": "http.request", "body": body, "more_body": False}
        await asyncio.Event().wait()  # like a real connection: stay open until the response finishes

    async def send(msg):
        if msg["type"] == "http.response.start":
            out["status"] = msg["status"]
            out["headers"] = {k.decode().lower(): v.decode() for k, v in msg["headers"]}
        elif msg["type"] == "http.response.body":
            out["body"] += msg.get("body", b"")

    asyncio.run(app(scope, receive, send))
    return Resp(out["status"], out["headers"], out["body"])
