"""Secured HTTP API + web app host (Starlette, the framework FastAPI is built on).

Controls: API-key auth with roles (viewer < analyst < admin), hashed keys, constant-time compare,
per-identity rate limiting, request-size caps, strict input validation, security headers + CSP,
request IDs, structured access logs, Prometheus metrics, generic error messages, audit logging,
safe static file serving, fail-closed startup in production without keys.
"""
from __future__ import annotations

import json
import logging
import os
import re
import sys
import time
import uuid
from collections import defaultdict
from pathlib import Path

from starlette.applications import Starlette
from starlette.requests import Request
from starlette.responses import FileResponse, JSONResponse, PlainTextResponse, Response, StreamingResponse
from starlette.routing import Route

from . import __version__, config
from .errors import NotFound
from .security import ROLE_RANK, ApiKeyStore, AuditLedger, RateLimiter, SQLGuardError
from .seo import CSP_STATIC, Site, normalise_api_url

API_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Cache-Control": "no-store",
    "Content-Security-Policy": "default-src 'none'; frame-ancestors 'none'",
}
STATIC_CSP = CSP_STATIC  # one definition, shared with the static export
STATIC_MIME = {
    ".html": "text/html; charset=utf-8", ".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8",
    ".json": "application/json", ".webmanifest": "application/manifest+json", ".svg": "image/svg+xml",
    ".png": "image/png", ".ico": "image/x-icon", ".txt": "text/plain; charset=utf-8", ".xml": "application/xml",
}
_REQUEST_ID = re.compile(r"^[A-Za-z0-9\-]{8,64}$")


class ApiError(Exception):
    def __init__(self, status: int, message: str, headers: dict | None = None):
        self.status, self.message, self.headers = status, message, headers or {}


def _json(data, status: int = 200, headers: dict | None = None) -> JSONResponse:
    return JSONResponse(data, status_code=status, headers={**API_HEADERS, **(headers or {})})


async def _read_body(request: Request, limit: int) -> bytes:
    declared = request.headers.get("content-length")
    if declared and declared.isdigit() and int(declared) > limit:
        raise ApiError(413, "Request body too large.")
    chunks, size = [], 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > limit:
            raise ApiError(413, "Request body too large.")
        chunks.append(chunk)
    return b"".join(chunks)


async def _json_body(request: Request) -> dict:
    if "application/json" not in request.headers.get("content-type", ""):
        raise ApiError(415, "Content-Type must be application/json.")
    try:
        data = json.loads((await _read_body(request, config.MAX_BODY_BYTES)) or b"{}")
    except ValueError:
        raise ApiError(400, "Body is not valid JSON.") from None
    if not isinstance(data, dict):
        raise ApiError(400, "JSON body must be an object.")
    return data


def _text_field(data: dict, name: str, max_len: int) -> str:
    v = data.get(name)
    if not isinstance(v, str) or not v.strip():
        raise ApiError(422, f"'{name}' must be a non-empty string.")
    if len(v) > max_len:
        raise ApiError(422, f"'{name}' is longer than {max_len} characters.")
    return v


def _int_param(request: Request, name: str, default: int, lo: int, hi: int) -> int:
    raw = request.query_params.get(name)
    if raw is None:
        return default
    if not raw.lstrip("-").isdigit():
        raise ApiError(422, f"'{name}' must be an integer.")
    return max(lo, min(int(raw), hi))


def _access_logger() -> logging.Logger:
    log = logging.getLogger("retailpulse.access")
    if not log.handlers:
        h = logging.StreamHandler(sys.stdout)
        h.setFormatter(logging.Formatter("%(message)s"))
        log.addHandler(h)
        log.setLevel(logging.INFO)
        log.propagate = False
    return log


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, default=str)}\n\n"


def create_app(paths: config.Paths | None = None, keys: ApiKeyStore | None = None,
               rate_limiter: RateLimiter | None = None, env: str | None = None,
               web_dir: Path | None = None) -> Starlette:
    paths = paths or config.Paths.default()
    env = env or config.ENV
    keys = keys if keys is not None else ApiKeyStore.from_env(os.getenv("RP_API_KEYS"))
    if env == "prod" and not keys.entries:
        raise RuntimeError("RP_ENV=prod requires RP_API_KEYS (run: python -m retailpulse.cli make-key).")
    web_root = Path(web_dir or config.WEB_DIR).resolve()
    limiter = rate_limiter or RateLimiter()
    log = _access_logger()
    started = time.time()
    state: dict = {"svc": None, "ledger": None}
    metrics = {"req": defaultdict(int), "dur_sum": defaultdict(float), "dur_cnt": defaultdict(int),
               "auth_failed": 0, "rate_limited": 0}

    def ledger() -> AuditLedger:
        if state["ledger"] is None:
            state["ledger"] = AuditLedger(paths.audit_log)
        return state["ledger"]

    def service():
        if state["svc"] is None:
            from .service import RetailPulseService
            try:
                state["svc"] = RetailPulseService(paths, ledger=ledger())
            except FileNotFoundError:
                raise ApiError(503, "Service not ready: run the pipeline first.") from None
        return state["svc"]

    def authenticate(request: Request, min_role: str) -> tuple[str, str]:
        host = request.client.host if request.client else "unknown"
        ok, wait = limiter.allow(f"ip:{host}")
        if not ok:
            metrics["rate_limited"] += 1
            raise ApiError(429, "Too many requests.", {"Retry-After": str(int(wait) + 1)})
        if not keys.entries:  # dev convenience only; prod refuses to start without keys
            actor, role = "dev-anonymous", "admin"
        else:
            header = request.headers.get("authorization", "")
            presented = header[7:].strip() if header.lower().startswith("bearer ") else request.headers.get("x-api-key")
            actor = keys.verify(presented)
            if actor is None:
                metrics["auth_failed"] += 1
                ledger().append(f"ip:{host}", "auth_failed", {"path": request.url.path})
                raise ApiError(401, "Missing or invalid API key.", {"WWW-Authenticate": "Bearer"})
            role = keys.role_of(actor)
        ok, wait = limiter.allow(f"key:{actor}")
        if not ok:
            metrics["rate_limited"] += 1
            raise ApiError(429, "Rate limit exceeded.", {"Retry-After": str(int(wait) + 1)})
        if ROLE_RANK[role] < ROLE_RANK[min_role]:
            ledger().append(actor, "forbidden", {"path": request.url.path, "role": role, "needs": min_role})
            raise ApiError(403, f"This endpoint needs the '{min_role}' role.")
        return actor, role

    # ------------------------------------------------------------------ route registry
    specs: list[dict] = []

    def route(path, method, summary, role="viewer", public=False, params=None, body=None, tag="analytics"):
        def deco(fn):
            specs.append({"path": path, "method": method, "summary": summary, "role": role, "public": public,
                          "params": params or [], "body": body, "tag": tag, "fn": fn})
            return fn
        return deco

    def make_handler(spec: dict):
        async def handler(request: Request):
            t0 = time.monotonic()
            rid = request.headers.get("x-request-id", "")
            rid = rid if _REQUEST_ID.match(rid) else uuid.uuid4().hex[:16]
            actor, role, status = "anonymous", "-", 500
            try:
                if spec["public"]:
                    actor = "public"
                else:
                    actor, role = authenticate(request, spec["role"])
                result = await spec["fn"](request, actor, role)
                status = getattr(result, "status_code", 200)
                resp = result if isinstance(result, Response) else _json(result)
                for k, v in API_HEADERS.items():
                    resp.headers.setdefault(k, v)
            except ApiError as e:
                status = e.status
                resp = _json({"error": e.message}, e.status, e.headers)
            except SQLGuardError as e:
                status, resp = 400, _json({"error": str(e)}, 400)
            except NotFound as e:
                status, resp = 404, _json({"error": str(e)}, 404)
            except ValueError as e:  # service-level validation (clear, safe messages)
                status, resp = 422, _json({"error": str(e)}, 422)
            except Exception:  # never leak internals
                status, resp = 500, _json({"error": "Internal server error."}, 500)
            ms = (time.monotonic() - t0) * 1000
            resp.headers["X-Request-ID"] = rid
            key = (request.method, spec["path"], status)
            metrics["req"][key] += 1
            metrics["dur_sum"][(request.method, spec["path"])] += ms / 1000
            metrics["dur_cnt"][(request.method, spec["path"])] += 1
            log.info(json.dumps({"ts": round(time.time(), 3), "rid": rid, "actor": actor, "role": role,
                                 "method": request.method, "path": request.url.path, "status": status,
                                 "ms": round(ms, 1)}))
            if not spec["public"]:
                try:
                    ledger().append(actor, "http", {"method": request.method, "path": request.url.path,
                                                    "status": status, "ms": round(ms, 1), "rid": rid})
                except Exception:
                    pass
            return resp
        return handler

    # ------------------------------------------------------------------ endpoints
    P_N = {"name": "n", "in": "query", "schema": {"type": "integer"}, "description": "Row limit"}

    @route("/health", "GET", "Liveness and mode (public)", public=True, tag="system")
    async def health(request, actor, role):
        base = {"version": __version__, "auth_required": bool(keys.entries), "env": env, "mode": "live"}
        try:
            return {**service().health(), **base, "ready": True}
        except ApiError:
            return {"status": "starting", "ready": False, **base}

    @route("/v1/me", "GET", "Who am I (actor + role)", tag="system")
    async def me(request, actor, role):
        return {"actor": actor, "role": role, "auth_required": bool(keys.entries)}

    @route("/v1/kpis", "GET", "Headline KPIs")
    async def kpis(request, actor, role):
        return service().kpis()

    @route("/v1/summary", "GET", "Pipeline summary: data, models, evals", tag="mlops")
    async def summary(request, actor, role):
        s = dict(service().summary())
        s.pop("registry", None)
        return s

    @route("/v1/monthly", "GET", "Monthly net revenue, profit, orders")
    async def monthly(request, actor, role):
        return service().monthly()

    @route("/v1/top", "GET", "Top-N by dimension and metric", params=[
        {"name": "dimension", "in": "query", "schema": {"type": "string"}},
        {"name": "metric", "in": "query", "schema": {"type": "string"}}, P_N,
        {"name": "order", "in": "query", "schema": {"type": "string", "enum": ["asc", "desc"]}}])
    async def top(request, actor, role):
        q = request.query_params
        return service().top_n(q.get("dimension", "category"), q.get("metric", "revenue"),
                               _int_param(request, "n", 5, 1, 20), q.get("order") == "asc")

    @route("/v1/forecast", "GET", "Daily revenue forecast with bands", params=[
        {"name": "horizon", "in": "query", "schema": {"type": "integer", "minimum": 1, "maximum": 60}}])
    async def forecast(request, actor, role):
        return service().forecast(_int_param(request, "horizon", 14, 1, 60))

    @route("/v1/segments", "GET", "RFM segment summary")
    async def segments(request, actor, role):
        return service().segments()

    @route("/v1/cohort", "GET", "Cohort retention matrix")
    async def cohort(request, actor, role):
        return service().cohort()

    @route("/v1/anomalies", "GET", "Flagged anomalous days (order volume)")
    async def anomalies(request, actor, role):
        return service().anomalies()

    @route("/v1/basket", "GET", "Category pairs by lift", params=[P_N])
    async def basket(request, actor, role):
        return service().basket(_int_param(request, "n", 15, 1, 30))

    @route("/v1/named", "GET", "List the named SQL library")
    async def named_list(request, actor, role):
        return {"queries": service().named_list()}

    @route("/v1/named/{name}", "GET", "Run one named SQL query through the guard",
           params=[{"name": "name", "in": "path", "required": True, "schema": {"type": "string"}}])
    async def named(request, actor, role):
        return service().named(request.path_params["name"])

    @route("/v1/churn/top", "GET", "Highest value-at-risk customers (anonymous keys)", role="analyst", params=[P_N],
           tag="customers")
    async def churn_top(request, actor, role):
        return service().churn_top(_int_param(request, "n", 10, 1, 50))

    @route("/v1/customers/{key}", "GET", "Customer 360 (no PII)", role="analyst", tag="customers",
           params=[{"name": "key", "in": "path", "required": True, "schema": {"type": "integer"}}])
    async def customer(request, actor, role):
        return service().customer360(request.path_params["key"])

    @route("/v1/monitoring", "GET", "Drift report (PSI)", tag="mlops")
    async def monitoring(request, actor, role):
        return service().monitoring()

    @route("/v1/models", "GET", "Model registry (versions, metrics, gates)", tag="mlops")
    async def models(request, actor, role):
        return service().models()

    @route("/v1/sql", "POST", "Guarded read-only SQL", role="analyst", tag="ai", body="{sql: string}")
    async def sql(request, actor, role):
        data = await _json_body(request)
        return service().safe_query(_text_field(data, "sql", 2000), actor=actor)

    @route("/v1/ask", "POST", "RAG answer with citations", tag="ai", body="{question: string}")
    async def ask(request, actor, role):
        data = await _json_body(request)
        return service().ask(_text_field(data, "question", 500), actor=actor)

    @route("/v1/agent", "POST", "Tool-using agent (single response)", role="analyst", tag="ai", body="{question: string}")
    async def agent(request, actor, role):
        data = await _json_body(request)
        return service().run_agent(_text_field(data, "question", 500), actor=actor)

    @route("/v1/agent/stream", "POST", "Tool-using agent as a Server-Sent Events stream", role="analyst", tag="ai",
           body="{question: string}")
    async def agent_stream(request, actor, role):
        data = await _json_body(request)
        question = _text_field(data, "question", 500)
        svc = service()

        def gen():
            from .agent import AnalyticsAgent
            try:
                for ev in AnalyticsAgent(svc, ledger=svc.ledger, llm=svc.llm).stream(question, actor=actor):
                    yield _sse(ev["type"], ev)
            except Exception:
                yield _sse("error", {"type": "error", "message": "Internal error while running the agent."})
            yield _sse("done", {"type": "done"})

        return StreamingResponse(gen(), media_type="text/event-stream",
                                 headers={"Cache-Control": "no-store", "X-Accel-Buffering": "no"})

    @route("/v1/classify", "POST", "Classify a PNG/JPEG product tile (raw body)", tag="ai",
           body="raw image/png or image/jpeg")
    async def classify(request, actor, role):
        ctype = request.headers.get("content-type", "").split(";")[0].strip()
        if ctype not in ("image/png", "image/jpeg"):
            raise ApiError(415, "Send the raw image with Content-Type image/png or image/jpeg.")
        data = await _read_body(request, config.MAX_IMAGE_BYTES)
        return service().classify_image(data, actor=actor)

    @route("/v1/audit/verify", "GET", "Verify the audit hash chain", role="admin", tag="security")
    async def audit_verify(request, actor, role):
        ok, bad = ledger().verify()
        return {"ok": ok, "first_bad_line": bad}

    @route("/v1/audit/tail", "GET", "Recent audit entries", role="admin", tag="security", params=[P_N])
    async def audit_tail(request, actor, role):
        return service().audit_tail(_int_param(request, "n", 30, 1, 200))

    @route("/metrics", "GET", "Prometheus metrics", role="admin", tag="system")
    async def metrics_endpoint(request, actor, role):
        out = ["# HELP rp_http_requests_total HTTP requests", "# TYPE rp_http_requests_total counter"]
        for (m, p, s), v in sorted(metrics["req"].items()):
            out.append(f'rp_http_requests_total{{method="{m}",path="{p}",status="{s}"}} {v}')
        out += ["# HELP rp_http_request_duration_seconds Request latency", "# TYPE rp_http_request_duration_seconds summary"]
        for (m, p), v in sorted(metrics["dur_sum"].items()):
            out.append(f'rp_http_request_duration_seconds_sum{{method="{m}",path="{p}"}} {v:.6f}')
            out.append(f'rp_http_request_duration_seconds_count{{method="{m}",path="{p}"}} {metrics["dur_cnt"][(m, p)]}')
        out += ["# TYPE rp_auth_failures_total counter", f"rp_auth_failures_total {metrics['auth_failed']}",
                "# TYPE rp_rate_limited_total counter", f"rp_rate_limited_total {metrics['rate_limited']}",
                "# TYPE rp_uptime_seconds gauge", f"rp_uptime_seconds {time.time() - started:.0f}"]
        return PlainTextResponse("\n".join(out) + "\n", media_type="text/plain; version=0.0.4")

    # ------------------------------------------------------------------ OpenAPI
    def openapi() -> dict:
        paths: dict = {}
        for s in specs:
            op = {"summary": s["summary"], "tags": [s["tag"]], "x-required-role": "public" if s["public"] else s["role"],
                  "parameters": s["params"], "responses": {"200": {"description": "OK"}}}
            if not s["public"]:
                op["security"] = [{"bearerAuth": []}]
                op["responses"].update({"401": {"description": "Missing/invalid key"}, "403": {"description": "Role too low"},
                                        "429": {"description": "Rate limited"}})
            if s["body"]:
                op["requestBody"] = {"required": True, "description": s["body"]}
            paths.setdefault(s["path"], {})[s["method"].lower()] = op
        return {"openapi": "3.1.0",
                "info": {"title": "RetailPulse API", "version": __version__,
                         "description": "Read-only analytics + guarded AI. Roles: viewer < analyst < admin."},
                "servers": [{"url": "/"}],
                "components": {"securitySchemes": {"bearerAuth": {"type": "http", "scheme": "bearer"}}},
                "paths": paths}

    async def openapi_json(request: Request):
        return _json(openapi(), headers={"Cache-Control": "no-cache"})

    # ------------------------------------------------------------------ static web app
    try:
        site = Site(web_root)  # live server: pages are rendered but marked noindex, with no canonical URL
    except (OSError, ValueError, KeyError):
        site = None

    def html_page(page, status=200):
        headers = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                   "Content-Security-Policy": STATIC_CSP, "Cache-Control": "no-cache"}
        return Response(site.render(page), status_code=status, media_type="text/html; charset=utf-8", headers=headers)

    async def static(request: Request):
        if site is not None:
            page = site.match(request.url.path)
            if page is not None:
                return html_page(page)
            if request.url.path == "/404.html":
                return html_page(site.not_found, 404)
        rel = request.path_params.get("path", "") or "index.html"
        if rel.endswith("/"):
            rel += "index.html"
        try:
            target = (web_root / rel).resolve()
            parts_ok = not any(p.startswith(".") for p in Path(rel).parts)
            ok = parts_ok and target.is_file() and target.is_relative_to(web_root) and target.suffix in STATIC_MIME
        except (OSError, ValueError):
            ok = False
        if not ok:
            last_segment = request.url.path.rstrip("/").rsplit("/", 1)[-1]
            wants_html = "text/html" in request.headers.get("accept", "") and "." not in last_segment
            if site is not None and wants_html:
                return html_page(site.not_found, 404)  # a person following a bad link gets a real page
            return _json({"error": "Not found."}, 404)
        headers = {"X-Content-Type-Options": "nosniff", "X-Frame-Options": "DENY", "Referrer-Policy": "no-referrer",
                   "Content-Security-Policy": STATIC_CSP,
                   "Cache-Control": "no-cache" if target.suffix in (".html", ".webmanifest") or target.name == "sw.js"
                   else "public, max-age=3600"}
        return FileResponse(target, media_type=STATIC_MIME[target.suffix], headers=headers)

    routes = [Route(s["path"].replace("{key}", "{key:int}"), make_handler(s), methods=[s["method"]]) for s in specs]
    routes += [Route("/openapi.json", openapi_json, methods=["GET"]),
               Route("/", static, methods=["GET"]),
               Route("/{path:path}", static, methods=["GET"])]

    async def not_found(request, exc):
        return _json({"error": "Not found."}, 404)

    async def method_not_allowed(request, exc):
        return _json({"error": "Method not allowed."}, 405)

    # CORS is OFF unless RP_CORS_ORIGINS lists exact origins (never "*"): the static site on a CDN may call this API.
    middleware = []
    origins = [normalise_api_url(o) for o in os.getenv("RP_CORS_ORIGINS", "").split(",") if o.strip()]
    if any("*" in o for o in os.getenv("RP_CORS_ORIGINS", "").split(",")):
        raise RuntimeError("RP_CORS_ORIGINS must list exact origins; a wildcard is not allowed.")
    if origins:
        from starlette.middleware import Middleware
        from starlette.middleware.cors import CORSMiddleware
        middleware.append(Middleware(
            CORSMiddleware, allow_origins=origins, allow_methods=["GET", "POST", "OPTIONS"],
            allow_headers=["Authorization", "Content-Type", "X-Request-ID"],
            expose_headers=["Retry-After", "X-Request-ID"], allow_credentials=False, max_age=600))

    app = Starlette(routes=routes, middleware=middleware, exception_handlers={404: not_found, 405: method_not_allowed})
    app.state.openapi = openapi
    app.state.specs = specs
    return app


def _default_app():
    return create_app()  # fails closed in prod without keys


app = _default_app()
