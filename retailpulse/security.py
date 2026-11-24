"""Security building blocks (all stdlib, all unit-tested):

* SafeSQL        - read-only, allow-listed, PII-blind, time/row-limited SQL execution
* mask_pii       - redact e-mails / phone numbers in any text leaving the system
* detect_injection - heuristic prompt-injection / jailbreak detector
* RateLimiter    - token bucket per API identity
* ApiKeyStore    - API keys stored only as SHA-256 hashes, constant-time comparison
* AuditLedger    - tamper-evident hash-chained audit log
"""
from __future__ import annotations

import hashlib
import hmac
import json
import re
import secrets
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

from . import config

# --------------------------------------------------------------------- SQL guard
ALLOWED_TABLES = frozenset({"dim_customer", "dim_product", "dim_date", "fact_orders",
                  "fact_order_items", "returns", "vw_sales"})
PII_COLUMNS = {"email", "phone"}
ALLOWED_FUNCTIONS = {
    "count", "sum", "avg", "min", "max", "total", "round", "abs", "coalesce", "ifnull", "nullif",
    "length", "lower", "upper", "substr", "substring", "trim", "ltrim", "rtrim", "instr", "typeof",
    "strftime", "date", "datetime", "julianday", "printf", "group_concat", "iif", "cast",
    "row_number", "rank", "dense_rank", "percent_rank", "cume_dist", "ntile",
    "lag", "lead", "first_value", "last_value", "nth_value",
}
_COMMENT = re.compile(r"(--[^\n]*|/\*.*?\*/)", re.S)
_FORBIDDEN = re.compile(
    r"\b(insert|update|delete|drop|alter|create|attach|detach|pragma|replace|vacuum|reindex|"
    r"truncate|grant|revoke|load_extension|sqlite_master|sqlite_schema|sqlite_temp_master)\b", re.I)


_CTE_NAME = re.compile(r"(?is)(?:\bwith\s+(?:recursive\s+)?|,\s*)([A-Za-z_]\w*)\s*(?:\([^)]*\))?\s+as\s*(?:not\s+materialized\s*|materialized\s*)?\(")


def cte_names(cleaned_sql: str) -> set[str]:
    return {m.group(1).lower() for m in _CTE_NAME.finditer(cleaned_sql)}


class SQLGuardError(ValueError):
    """Raised when a query violates the read-only / allow-list policy."""


def validate_sql_text(sql: str, max_len: int = 2000) -> str:
    if not isinstance(sql, str) or not sql.strip():
        raise SQLGuardError("Empty query.")
    if len(sql) > max_len:
        raise SQLGuardError(f"Query too long (max {max_len} characters).")
    cleaned = _COMMENT.sub(" ", sql).strip().rstrip(";").strip()
    if ";" in cleaned:
        raise SQLGuardError("Only a single statement is allowed.")
    if not re.match(r"(?is)^(select|with)\b", cleaned):
        raise SQLGuardError("Only SELECT queries are allowed.")
    m = _FORBIDDEN.search(cleaned)
    if m:
        raise SQLGuardError(f"Forbidden keyword: {m.group(0).upper()}.")
    if re.search(r"\bsqlite_\w*", cleaned, re.I):
        raise SQLGuardError("Access to SQLite internals is not allowed.")
    return cleaned


class SafeSQL:
    """Defense in depth: (1) text validation, (2) read-only connection,
    (3) SQLite authorizer allow-listing tables/functions and nulling PII columns,
    (4) progress-handler timeout, (5) row cap, (6) PII masking on output."""

    def __init__(self, db_path, max_rows: int | None = None, timeout_s: float | None = None):
        self.db_path = Path(db_path)
        self.max_rows = max_rows or config.SQL_MAX_ROWS
        self.timeout_s = timeout_s or config.SQL_TIMEOUT_S

    @staticmethod
    def _make_authorizer(extra_tables: frozenset[str]):
        allowed = ALLOWED_TABLES | extra_tables  # extra = CTE names declared in THIS query

        def authorizer(action, arg1, arg2, dbname, source):
            if action in (sqlite3.SQLITE_SELECT, sqlite3.SQLITE_RECURSIVE):
                return sqlite3.SQLITE_OK
            if action == sqlite3.SQLITE_FUNCTION:
                return sqlite3.SQLITE_OK if (arg2 or "").lower() in ALLOWED_FUNCTIONS else sqlite3.SQLITE_DENY
            if action == sqlite3.SQLITE_READ:
                if (arg1 or "").lower() not in allowed:
                    return sqlite3.SQLITE_DENY
                if (arg2 or "").lower() in PII_COLUMNS:
                    return sqlite3.SQLITE_IGNORE  # column reads as NULL
                return sqlite3.SQLITE_OK
            return sqlite3.SQLITE_DENY

        return authorizer

    def query(self, sql: str) -> dict:
        cleaned = validate_sql_text(sql)
        conn = sqlite3.connect(self.db_path.resolve().as_uri() + "?mode=ro", uri=True)
        deadline = time.monotonic() + self.timeout_s
        conn.set_authorizer(self._make_authorizer(frozenset(cte_names(cleaned))))
        conn.set_progress_handler(lambda: 1 if time.monotonic() > deadline else 0, 1000)
        started = time.monotonic()
        try:
            cur = conn.execute(cleaned)
            cols = [d[0] for d in cur.description] if cur.description else []
            rows = cur.fetchmany(self.max_rows + 1)
        except sqlite3.OperationalError as e:
            msg = str(e).lower()
            if "interrupted" in msg:
                raise SQLGuardError(f"Query exceeded the {self.timeout_s}s time limit.") from None
            raise SQLGuardError(f"SQL error: {e}") from None
        except sqlite3.DatabaseError as e:
            if "not authorized" in str(e).lower():
                raise SQLGuardError("Query touches a table, column or function that is not allowed.") from None
            raise SQLGuardError(f"SQL error: {e}") from None
        finally:
            conn.close()
        truncated = len(rows) > self.max_rows
        rows = [[mask_pii(v) if isinstance(v, str) else v for v in r] for r in rows[: self.max_rows]]
        return {"columns": cols, "rows": rows, "row_count": len(rows), "truncated": truncated,
                "elapsed_ms": round((time.monotonic() - started) * 1000, 1)}


# --------------------------------------------------------------------- PII + injection
_EMAIL = re.compile(r"[\w.+-]+@[\w-]+\.[\w.-]+")
_PHONE = re.compile(r"(?<!\d)(?:\+?91[-\s]?)?[6-9]\d{9}(?!\d)")


def mask_pii(text: str) -> str:
    return _PHONE.sub("[phone]", _EMAIL.sub("[email]", text))


_INJECTION_PATTERNS = {
    "override_instructions": r"(ignore|disregard|forget|override)\b.{0,40}\b(previous|prior|above|earlier|all|your)\b.{0,30}\b(instructions?|rules?|prompts?|guardrails?)",
    "reveal_prompt": r"(reveal|show|print|repeat|leak)\b.{0,30}\b(system prompt|instructions|hidden prompt|api[_ ]?key|secret|password|token)",
    "role_hijack": r"\byou are now\b|\bpretend (to be|you are)\b|\bdeveloper mode\b|\bjailbreak\b|\bDAN mode\b",
    "disable_safety": r"(disable|bypass|turn off|remove)\b.{0,20}\b(safety|guardrails?|filters?|security|authorization)",
}
_INJECTION_RE = {k: re.compile(v, re.I | re.S) for k, v in _INJECTION_PATTERNS.items()}


def detect_injection(text: str) -> list[str]:
    """Heuristic only: returns the names of matched patterns (empty list = nothing found)."""
    return [name for name, rx in _INJECTION_RE.items() if rx.search(text or "")]


# --------------------------------------------------------------------- rate limit
class RateLimiter:
    """Token bucket: `per_minute` sustained rate with a burst allowance."""

    def __init__(self, per_minute: int | None = None, burst: int | None = None, clock=time.monotonic):
        self.rate = (per_minute or config.RATE_LIMIT_PER_MIN) / 60.0
        self.capacity = float(burst or per_minute or config.RATE_LIMIT_PER_MIN)
        self.clock = clock
        self._buckets: dict[str, tuple[float, float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> tuple[bool, float]:
        now = self.clock()
        with self._lock:
            tokens, last = self._buckets.get(key, (self.capacity, now))
            tokens = min(self.capacity, tokens + (now - last) * self.rate)
            if tokens >= 1.0:
                self._buckets[key] = (tokens - 1.0, now)
                self._prune(now)
                return True, 0.0
            self._buckets[key] = (tokens, now)
            return False, (1.0 - tokens) / self.rate

    def _prune(self, now: float) -> None:
        if len(self._buckets) > 10_000:  # bound memory
            for k in [k for k, (t, last) in self._buckets.items() if now - last > 600]:
                self._buckets.pop(k, None)


# --------------------------------------------------------------------- API keys
def hash_key(key: str) -> str:
    return hashlib.sha256(key.encode("utf-8")).hexdigest()


def generate_api_key() -> tuple[str, str]:
    key = "rp_" + secrets.token_urlsafe(32)
    return key, hash_key(key)


ROLES = ("viewer", "analyst", "admin")  # increasing privilege
ROLE_RANK = {r: i for i, r in enumerate(ROLES)}


class ApiKeyStore:
    """Holds only hashes. Env format: RP_API_KEYS="name:sha256hex[:role],other:sha256hex:viewer".
    Role defaults to 'analyst'. Unknown roles are rejected (the entry is ignored)."""

    def __init__(self, entries: dict[str, str] | None = None, roles: dict[str, str] | None = None):
        self.entries = dict(entries or {})
        self.roles = {n: (roles or {}).get(n, "analyst") for n in self.entries}

    @classmethod
    def from_env(cls, value: str | None) -> "ApiKeyStore":
        entries, roles = {}, {}
        for part in (value or "").split(","):
            bits = part.strip().split(":")
            if len(bits) < 2 or len(bits) > 3:
                continue
            name, digest = bits[0], bits[1].lower()
            role = bits[2].lower() if len(bits) == 3 else "analyst"
            if name and re.fullmatch(r"[0-9a-f]{64}", digest) and role in ROLE_RANK:
                entries[name], roles[name] = digest, role
        return cls(entries, roles)

    def verify(self, presented: str | None) -> str | None:
        if not presented or len(presented) > 256:
            return None
        digest = hash_key(presented)
        match = None
        for name, stored in self.entries.items():  # check all entries: no early exit
            if hmac.compare_digest(digest, stored):
                match = name
        return match

    def role_of(self, name: str) -> str:
        return self.roles.get(name, "viewer")


# --------------------------------------------------------------------- audit ledger
def _sanitize(value, depth: int = 0):
    if depth > 4:
        return "..."
    if isinstance(value, str):
        return mask_pii(value)[:500]
    if isinstance(value, dict):
        return {str(k)[:60]: _sanitize(v, depth + 1) for k, v in list(value.items())[:30]}
    if isinstance(value, (list, tuple)):
        return [_sanitize(v, depth + 1) for v in list(value)[:30]]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:200]


class AuditLedger:
    """Append-only JSONL where every entry commits to the previous one (SHA-256 chain).
    Editing or deleting a middle entry breaks verification. (Truncating the tail is not
    detectable by the chain alone; anchor the latest hash elsewhere for that.)"""

    GENESIS = "0" * 64

    def __init__(self, path):
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        self._last = self._read_last_hash()

    def _read_last_hash(self) -> str:
        if not self.path.exists():
            return self.GENESIS
        last = self.GENESIS
        with self.path.open("r", encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    last = json.loads(line)["hash"]
        return last

    @staticmethod
    def _digest(entry: dict) -> str:
        payload = json.dumps(entry, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(payload.encode("utf-8")).hexdigest()

    def append(self, actor: str, action: str, detail: dict | None = None) -> dict:
        with self._lock:
            entry = {
                "ts": datetime.now(timezone.utc).isoformat(timespec="milliseconds"),
                "actor": str(actor)[:80], "action": str(action)[:80],
                "detail": _sanitize(detail or {}), "prev": self._last,
            }
            entry["hash"] = self._digest(entry)
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(entry, sort_keys=True) + "\n")
            self._last = entry["hash"]
            return entry

    def verify(self) -> tuple[bool, int | None]:
        """Returns (ok, first_bad_line_number)."""
        prev = self.GENESIS
        if not self.path.exists():
            return True, None
        with self.path.open("r", encoding="utf-8") as fh:
            for n, line in enumerate(fh, start=1):
                if not line.strip():
                    continue
                try:
                    entry = json.loads(line)
                except json.JSONDecodeError:
                    return False, n
                claimed = entry.pop("hash", None)
                if entry.get("prev") != prev or self._digest(entry) != claimed:
                    return False, n
                prev = claimed
        return True, None
