"""Model router (fake network) and the MCP stdio server (protocol level)."""
import io
import json

import pytest

from retailpulse.mcp_server import SUPPORTED, TOOLS, McpServer, ToolInputError, validate
from retailpulse.model_router import GEMINI_URL, GROQ_URL, AutoModelRouter
from retailpulse.security import AuditLedger
from retailpulse.service import RetailPulseService

KEY_G, KEY_M = "gsk_TESTKEY_abcdefghijkl", "AIza_TESTKEY_abcdefghijkl"


def fake_fetch(calls, fail=()):
    def fetch(url, headers, timeout):
        calls.append((url, dict(headers)))
        if url.split("/")[2] in fail:
            raise ConnectionError(f"boom {headers}")  # message holds the key: it must never be surfaced
        if url == GROQ_URL:
            return {"data": [{"id": "llama-3.3-70b-versatile"}, {"id": "whisper-large-v3"}, {"id": "llama-guard-4"},
                             {"id": "gemma2-9b-it"}, {"id": "llama-3.1-8b-instant"}]}
        return {"models": [{"name": "models/gemini-2.0-flash", "supportedGenerationMethods": ["generateContent"]},
                           {"name": "models/text-embedding-004", "supportedGenerationMethods": ["embedContent"]},
                           {"name": "models/gemini-pro", "supportedGenerationMethods": ["generateContent"]}]}
    return fetch


# ------------------------------------------------------------------ router
def test_router_filters_and_prefers_fast_models():
    calls = []
    r = AutoModelRouter(fetch=fake_fetch(calls), env={"GROQ_API_KEY": KEY_G, "GEMINI_API_KEY": KEY_M})
    found = r.discover_models()
    assert "whisper-large-v3" not in found["groq"] and "llama-guard-4" not in found["groq"]
    assert found["gemini"] == ["gemini-2.0-flash", "gemini-pro"]
    assert r.pick_model() == {"provider": "groq", "model": "llama-3.1-8b-instant", "mode": "live"}
    assert r.pick_model("gemini")["model"] == "gemini-2.0-flash"
    sent = dict(calls)
    assert sent[GROQ_URL]["Authorization"] == f"Bearer {KEY_G}" and sent[GEMINI_URL]["x-goog-api-key"] == KEY_M


def test_router_caches_until_ttl_and_force_refreshes():
    calls, now = [], [1000.0]
    r = AutoModelRouter(ttl_seconds=60, fetch=fake_fetch(calls), env={"GROQ_API_KEY": KEY_G}, clock=lambda: now[0])
    r.discover_models(); r.discover_models()
    assert len(calls) == 1
    now[0] += 61; r.discover_models()
    assert len(calls) == 2
    r.discover_models(force=True)
    assert len(calls) == 3


def test_router_degrades_to_offline_and_never_leaks_keys():
    r = AutoModelRouter(fetch=fake_fetch([], fail=("api.groq.com", "generativelanguage.googleapis.com")),
                        env={"GROQ_API_KEY": KEY_G, "GEMINI_API_KEY": KEY_M})
    assert r.pick_model() == {"provider": "local", "model": "deterministic-sql-fallback", "mode": "offline"}
    shown = repr(r) + json.dumps(r.status())
    assert KEY_G not in shown and KEY_M not in shown and "ConnectionError" in shown
    assert not AutoModelRouter(fetch=fake_fetch([]), env={}).discover_models()["groq"]


def test_router_one_provider_down_still_uses_the_other():
    r = AutoModelRouter(fetch=fake_fetch([], fail=("api.groq.com",)), env={"GROQ_API_KEY": KEY_G, "GEMINI_API_KEY": KEY_M})
    assert r.pick_model()["provider"] == "gemini"


@pytest.mark.parametrize("bad", ["short", "has space in it 12345", "line\nbreak_12345678", "x" * 300, ""])
def test_router_ignores_malformed_keys_so_headers_cannot_be_injected(bad):
    calls = []
    AutoModelRouter(fetch=fake_fetch(calls), env={"GROQ_API_KEY": bad}).discover_models()
    assert calls == []


def test_router_default_fetcher_refuses_non_https():
    from retailpulse.model_router import _urllib_fetch
    with pytest.raises(ValueError):
        _urllib_fetch("http://example.com/", {}, 1)
    with pytest.raises(ValueError):
        _urllib_fetch("file:///etc/passwd", {}, 1)


# ------------------------------------------------------------------ MCP
@pytest.fixture()
def server(built, tmp_path):
    svc = RetailPulseService(built[0], ledger=AuditLedger(tmp_path / "audit.jsonl"))
    return McpServer(svc, router=AutoModelRouter(fetch=fake_fetch([]), env={"GROQ_API_KEY": KEY_G})), svc


def rpc(server, method, params=None, id_=1):
    msg = {"jsonrpc": "2.0", "id": id_, "method": method}
    if params is not None:
        msg["params"] = params
    return server.handle(msg)


def test_initialize_negotiates_version_and_lists_read_only_tools(server):
    s, _ = server
    r = rpc(s, "initialize", {"protocolVersion": "2025-03-26", "capabilities": {}, "clientInfo": {"name": "t"}})
    assert r["result"]["protocolVersion"] == "2025-03-26" and r["result"]["serverInfo"]["name"] == "retailpulse"
    assert rpc(s, "initialize", {"protocolVersion": "1999-01-01"})["result"]["protocolVersion"] == SUPPORTED[0]
    assert s.handle({"jsonrpc": "2.0", "method": "notifications/initialized"}) is None and s.initialized
    tools = rpc(s, "tools/list")["result"]["tools"]
    assert {t["name"] for t in tools} == {t["name"] for t in TOOLS}
    assert all(t["annotations"]["readOnlyHint"] and t["inputSchema"]["type"] == "object" for t in tools)
    assert rpc(s, "ping")["result"] == {}


def call(s, name, args=None):
    r = rpc(s, "tools/call", {"name": name, "arguments": args or {}})["result"]
    return r["isError"], r["content"][0]["text"]


def test_tools_return_real_service_data(server):
    s, svc = server
    err, text = call(s, "kpis"); assert not err and json.loads(text) == json.loads(json.dumps(svc.kpis(), default=str))
    err, text = call(s, "top_n", {"dimension": "category", "metric": "profit", "n": 3}); assert not err
    assert len(json.loads(text)["rows"]) == 3
    err, text = call(s, "forecast", {"horizon": 7}); assert not err and len(json.loads(text)["rows"]) == 7
    err, text = call(s, "churn_risk", {"n": 5}); assert not err and "email" not in text and "phone" not in text
    err, text = call(s, "search_docs", {"question": "How is churn defined?"}); assert not err and "churn" in text.lower()
    err, text = call(s, "list_models"); assert not err and KEY_G not in text and "llama" in text
    err, text = call(s, "run_sql", {"sql": "SELECT category, COUNT(*) n FROM dim_product GROUP BY category"}); assert not err


def test_guard_and_validation_failures_are_tool_errors_not_crashes(server):
    s, _ = server
    for sql in ["DROP TABLE returns", "SELECT * FROM sqlite_master", "SELECT 1; SELECT 2"]:
        err, text = call(s, "run_sql", {"sql": sql}); assert err and text.startswith("Rejected")
    err, text = call(s, "run_sql", {"sql": "SELECT email, phone FROM dim_customer LIMIT 3"})
    assert not err and all(v is None for row in json.loads(text)["rows"] for v in row)
    for name, args in [("top_n", {}), ("top_n", {"dimension": "nope"}), ("top_n", {"dimension": "city", "n": 999}),
                       ("top_n", {"dimension": "city", "n": True}), ("kpis", {"x": 1}),
                       ("search_docs", {"question": 7}), ("forecast", {"horizon": 0})]:
        err, text = call(s, name, args); assert err and text.startswith("Rejected"), (name, args, text)


def test_protocol_errors(server):
    s, _ = server
    assert rpc(s, "tools/call", {"name": "rm_rf"})["error"]["code"] == -32602
    assert rpc(s, "nope/method")["error"]["code"] == -32601
    assert s.handle([1, 2])["error"]["code"] == -32600
    assert s.handle({"jsonrpc": "1.0", "id": 4, "method": "ping"})["error"]["code"] == -32600
    assert rpc(s, "tools/call", ["x"])["error"]["code"] == -32602


def test_stdio_loop_is_line_delimited_and_survives_garbage(server):
    s, svc = server
    lines = [json.dumps({"jsonrpc": "2.0", "id": 1, "method": "initialize", "params": {"protocolVersion": SUPPORTED[0]}}),
             "{not json", "",
             json.dumps({"jsonrpc": "2.0", "method": "notifications/initialized"}),
             json.dumps({"jsonrpc": "2.0", "id": 2, "method": "tools/call", "params": {"name": "kpis", "arguments": {}}})]
    out = io.StringIO()
    s.serve(io.StringIO("\n".join(lines) + "\n"), out)
    replies = [json.loads(x) for x in out.getvalue().splitlines()]
    assert [r.get("id") for r in replies] == [1, None, 2] and replies[1]["error"]["code"] == -32700
    assert all("\n" not in x for x in out.getvalue().rstrip("\n").splitlines())
    assert svc.ledger.verify()[0] is True  # the ledger stays intact after a mixed session


def test_tool_calls_are_audited(server):
    s, svc = server
    call(s, "run_sql", {"sql": "SELECT 1"}); call(s, "search_docs", {"question": "What is RFM?"})
    text = svc.ledger.path.read_text()
    assert '"mcp"' in text and "sql_query" in text and "rag_ask" in text


def test_validate_helper_rejects_bad_shapes():
    schema = {"type": "object", "additionalProperties": False, "required": ["a"],
              "properties": {"a": {"type": "integer", "minimum": 1, "maximum": 3}}}
    assert validate({"a": 2}, schema) == {"a": 2}
    for bad in ([], {"a": "2"}, {"a": 4}, {}, {"a": 1, "b": 2}):
        with pytest.raises(ToolInputError):
            validate(bad, schema)
