"""A small, read-only Model Context Protocol (MCP) server over stdio.

Lets an MCP client (an IDE or desktop assistant) call RetailPulse tools. Transport: newline-delimited JSON-RPC 2.0
on stdin/stdout (logs go to stderr only). Run:  ``python -m retailpulse.cli mcp``

Safety: every tool is read-only and goes through the same service layer as the API and agent: SQL runs through the
SafeSQL guard (PII columns read as NULL), customers appear only as anonymous keys, arguments are validated against
each tool's schema, results are size-capped and every call is written to the hash-chained audit log. The process
runs with the privileges of the local user who started it; do not expose it on a network.

Limitation: covered by protocol-level unit tests (initialize, tools/list, tools/call, errors, stdio loop). It has
not been exercised against a real MCP client in the build environment.
"""
from __future__ import annotations

import json
import sys
from typing import Any, TextIO

from . import __version__
from .security import SQLGuardError

SUPPORTED = ("2025-06-18", "2025-03-26", "2024-11-05")
MAX_RESULT_CHARS = 200_000
DIMENSIONS = ["category", "city", "channel", "payment", "age_band", "product"]
METRICS = ["revenue", "profit", "orders", "units", "margin"]

TOOLS: list[dict[str, Any]] = [
    {"name": "kpis", "description": "Headline business KPIs (net revenue, profit, orders, AOV, return rate).",
     "inputSchema": {"type": "object", "properties": {}, "additionalProperties": False}},
    {"name": "top_n", "description": "Top groups by a metric, for example the top 5 categories by profit.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["dimension"], "properties": {
         "dimension": {"type": "string", "enum": DIMENSIONS}, "metric": {"type": "string", "enum": METRICS},
         "n": {"type": "integer", "minimum": 1, "maximum": 50}}}},
    {"name": "forecast", "description": "Daily net-revenue forecast with an empirical range, plus the backtest WAPE.",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "horizon": {"type": "integer", "minimum": 1, "maximum": 60}}}},
    {"name": "churn_risk", "description": "Highest value-at-risk customers (anonymous keys only, no personal data).",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {
         "n": {"type": "integer", "minimum": 1, "maximum": 50}}}},
    {"name": "search_docs", "description": "Ask the knowledge base; the answer cites its sources or abstains.",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["question"], "properties": {
         "question": {"type": "string", "minLength": 3, "maxLength": 500}}}},
    {"name": "run_sql", "description": "Run one read-only SELECT through the SQL guard (personal columns read as NULL).",
     "inputSchema": {"type": "object", "additionalProperties": False, "required": ["sql"], "properties": {
         "sql": {"type": "string", "minLength": 6, "maxLength": 2000}}}},
    {"name": "list_models", "description": "Which hosted LLMs are available if API keys are configured (never shows keys).",
     "inputSchema": {"type": "object", "additionalProperties": False, "properties": {}}},
]
_BY_NAME = {t["name"]: t for t in TOOLS}


class ToolInputError(ValueError):
    pass


def validate(args: Any, schema: dict) -> dict:
    """Validate the small JSON-Schema subset used above (object, string, integer, enum, bounds, required)."""
    if not isinstance(args, dict):
        raise ToolInputError("arguments must be an object")
    props = schema.get("properties", {})
    extra = set(args) - set(props)
    if extra and schema.get("additionalProperties") is False:
        raise ToolInputError(f"unknown argument(s): {', '.join(sorted(extra))}")
    for r in schema.get("required", []):
        if r not in args:
            raise ToolInputError(f"missing required argument: {r}")
    for k, v in args.items():
        s = props[k]
        if s["type"] == "integer":
            if isinstance(v, bool) or not isinstance(v, int):
                raise ToolInputError(f"{k} must be an integer")
            if not s.get("minimum", v) <= v <= s.get("maximum", v):
                raise ToolInputError(f"{k} must be between {s.get('minimum')} and {s.get('maximum')}")
        elif s["type"] == "string":
            if not isinstance(v, str):
                raise ToolInputError(f"{k} must be a string")
            if not s.get("minLength", 0) <= len(v) <= s.get("maxLength", len(v)):
                raise ToolInputError(f"{k} must be {s.get('minLength', 0)} to {s.get('maxLength')} characters")
            if "enum" in s and v not in s["enum"]:
                raise ToolInputError(f"{k} must be one of: {', '.join(s['enum'])}")
    return args


class McpServer:
    def __init__(self, service, router=None, actor: str = "mcp"):
        self.svc, self.router, self.actor = service, router, actor
        self.initialized = False

    # ------------------------------------------------------------------ tools
    def call_tool(self, name: str, args: dict) -> Any:
        tool = _BY_NAME[name]
        a = validate(args, tool["inputSchema"])
        s = self.svc
        if name == "kpis":
            return s.kpis()
        if name == "top_n":
            return s.top_n(a["dimension"], a.get("metric", "revenue"), a.get("n", 10))
        if name == "forecast":
            return s.forecast(a.get("horizon", 30))
        if name == "churn_risk":
            return s.churn_top(a.get("n", 10))
        if name == "search_docs":
            return s.ask(a["question"], actor=self.actor)
        if name == "run_sql":
            return s.safe_query(a["sql"], actor=self.actor)
        if name == "list_models":
            if self.router is None:
                return {"groq_configured": False, "gemini_configured": False, "models": {}, "pick": None}
            models = self.router.discover_models()
            return {**self.router.status(), "models": models, "pick": self.router.pick_model()}
        raise KeyError(name)

    # ------------------------------------------------------------------ protocol
    @staticmethod
    def _ok(id_: Any, result: dict) -> dict:
        return {"jsonrpc": "2.0", "id": id_, "result": result}

    @staticmethod
    def _err(id_: Any, code: int, message: str) -> dict:
        return {"jsonrpc": "2.0", "id": id_, "error": {"code": code, "message": message}}

    def handle(self, msg: Any) -> dict | None:
        """Return the response for one decoded message, or None for notifications."""
        if not isinstance(msg, dict) or msg.get("jsonrpc") != "2.0" or not isinstance(msg.get("method"), str):
            return self._err(msg.get("id") if isinstance(msg, dict) else None, -32600, "Invalid Request")
        method, id_, params = msg["method"], msg.get("id"), msg.get("params") or {}
        is_notification = "id" not in msg
        if is_notification:
            if method == "notifications/initialized":
                self.initialized = True
            return None
        if not isinstance(params, dict):
            return self._err(id_, -32602, "params must be an object")
        if method == "initialize":
            asked = params.get("protocolVersion")
            return self._ok(id_, {
                "protocolVersion": asked if asked in SUPPORTED else SUPPORTED[0],
                "capabilities": {"tools": {"listChanged": False}},
                "serverInfo": {"name": "retailpulse", "version": __version__},
                "instructions": "Read-only retail analytics over synthetic data. Customers are anonymous keys; "
                                "SQL runs through a guard that blocks writes and nulls personal columns."})
        if method == "ping":
            return self._ok(id_, {})
        if method == "tools/list":
            return self._ok(id_, {"tools": [{**t, "annotations": {"readOnlyHint": True, "openWorldHint": False}}
                                            for t in TOOLS]})
        if method == "tools/call":
            name = params.get("name")
            if name not in _BY_NAME:
                return self._err(id_, -32602, f"Unknown tool: {name!r}")
            try:
                text = json.dumps(self.call_tool(name, params.get("arguments") or {}), default=str)
                if len(text) > MAX_RESULT_CHARS:
                    raise ToolInputError("result too large; narrow the request")
                return self._ok(id_, {"content": [{"type": "text", "text": text}], "isError": False})
            except (ToolInputError, SQLGuardError) as e:
                return self._ok(id_, {"content": [{"type": "text", "text": f"Rejected: {e}"}], "isError": True})
            except Exception as e:  # noqa: BLE001 (never leak a stack trace to the client)
                print(f"[mcp] tool {name} failed: {type(e).__name__}", file=sys.stderr)
                return self._ok(id_, {"content": [{"type": "text", "text": "The tool failed. Check the server log."}],
                                      "isError": True})
        return self._err(id_, -32601, f"Method not found: {method}")

    def serve(self, rfile: TextIO = sys.stdin, wfile: TextIO = sys.stdout) -> None:
        for line in rfile:
            line = line.strip()
            if not line:
                continue
            try:
                msg = json.loads(line)
            except json.JSONDecodeError:
                out = self._err(None, -32700, "Parse error")
            else:
                out = self.handle(msg)
            if out is not None:
                wfile.write(json.dumps(out, separators=(",", ":")) + "\n")
                wfile.flush()
