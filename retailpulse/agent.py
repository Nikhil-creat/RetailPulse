"""Tool-using analytics agent with guardrails.

Loop: guard input -> plan -> act (allow-listed tools only, step budget) -> observe -> answer.
Every tool call is audit-logged. The default planner is rule-based and deterministic;
if an LLM is configured it may propose the plan, but the plan is validated against the same
tool allow-list and argument schemas, and falls back to the rule-based planner on any problem.
"""
from __future__ import annotations

import json
import re
import time

from . import config
from .catalog import DIMENSIONS, METRICS, MONEY_METRICS, inr
from .security import SQLGuardError, detect_injection, mask_pii

TOOLS = {"kpi_summary", "top_n", "sql_query", "forecast", "rfm_segments", "churn_risk", "search_knowledge"}

_WRITE = re.compile(r"\b(delete|drop|truncate|alter|insert into|update\s+\w+\s+set|modify the database)\b", re.I)
_PII_ASK = re.compile(r"\b(e-?mails?|phone|mobile number|contact details|home address|password|api[_ ]?keys?|secrets?)\b", re.I)

_DIM_WORDS = {"categor": "category", "cities": "city", "city": "city", "channel": "channel", "payment": "payment",
              "product": "product", "age": "age_band", "month": "month"}
_METRIC_WORDS = [("profit", "profit"), ("margin", "margin"), ("order", "orders"), ("unit", "units"),
                 ("sold", "units"), ("revenue", "revenue"), ("sales", "revenue")]


def _dimension(q: str) -> str | None:
    for word, dim in _DIM_WORDS.items():
        if word in q:
            return dim
    return None


def _metric(q: str) -> str:
    for word, m in _METRIC_WORDS:
        if word in q:
            return m
    return "revenue"


def _number(q: str, default: int) -> int:
    m = re.search(r"\b(?:top|best|worst|bottom|next|first)?\s*(\d{1,3})\b", q)
    return int(m.group(1)) if m else default


def plan(question: str) -> dict:
    """Rule-based planner. Returns {"refusal": str|None, "steps": [{"tool","args"}]}."""
    q = question.strip()
    ql = q.lower()
    flags = detect_injection(q)
    if flags:
        return {"refusal": "I can't follow instructions that try to override my rules or expose secrets.",
                "steps": [], "flags": flags}
    if _WRITE.search(ql):
        return {"refusal": "I'm read-only: I can analyse data but not change or delete it.", "steps": []}
    if _PII_ASK.search(ql):
        return {"refusal": "Customer contact details and credentials are not exposed. "
                           "I can answer using anonymous customer keys and aggregates instead.", "steps": []}
    if re.match(r"^\s*(select|with)\b", ql):
        return {"refusal": None, "steps": [{"tool": "sql_query", "args": {"sql": q}}]}

    steps: list[dict] = []
    if re.search(r"\b(forecast|predict|projection|next \d+ days|next (week|month)|expected sales)\b", ql):
        horizon = 7 if "week" in ql else 30 if "month" in ql else _number(ql, 14)
        steps.append({"tool": "forecast", "args": {"horizon": max(1, min(horizon, 60))}})
    if re.search(r"\b(rfm|segment|champion|loyal|hibernating)\b", ql):
        steps.append({"tool": "rfm_segments", "args": {}})
    if re.search(r"\b(churn|attrition|at[- ]risk|likely to leave)\b", ql):
        steps.append({"tool": "churn_risk", "args": {"n": min(_number(ql, 5), 20)}})
    dim = _dimension(ql)
    if dim and re.search(r"\b(top|best|highest|most|lowest|worst|bottom|rank|by|per|which|compare)\b", ql):
        ascending = bool(re.search(r"\b(lowest|worst|bottom|least)\b", ql))
        steps.append({"tool": "top_n", "args": {"dimension": dim, "metric": _metric(ql),
                                                "n": min(_number(ql, 5), 20), "ascending": ascending}})
    if not steps and re.search(r"\b(kpi|overview|summary|overall|total|how much|how many)\b", ql):
        steps.append({"tool": "kpi_summary", "args": {}})
    if re.search(r"\b(why|reason|explain|define|meaning|methodology|how (does|is|do|are))\b", ql) or not steps:
        steps.append({"tool": "search_knowledge", "args": {"question": q}})
    return {"refusal": None, "steps": steps}


def validate_plan(raw) -> list[dict] | None:
    """Accept an LLM-proposed plan only if every step is an allow-listed tool with sane args."""
    if not isinstance(raw, list) or not 1 <= len(raw) <= config.AGENT_MAX_STEPS:
        return None
    out = []
    for s in raw:
        if not isinstance(s, dict) or s.get("tool") not in TOOLS or not isinstance(s.get("args", {}), dict):
            return None
        a = s.get("args", {})
        if s["tool"] == "top_n" and (a.get("dimension") not in DIMENSIONS or a.get("metric", "revenue") not in METRICS):
            return None
        if s["tool"] == "sql_query" and not isinstance(a.get("sql"), str):
            return None
        out.append({"tool": s["tool"], "args": a})
    return out


class AnalyticsAgent:
    def __init__(self, service, ledger=None, llm=None, max_steps: int | None = None):
        self.svc = service
        self.ledger = ledger
        self.llm = llm
        self.max_steps = max_steps or config.AGENT_MAX_STEPS

    # ---- tools
    def _run_tool(self, tool: str, args: dict):
        if tool == "kpi_summary":
            return self.svc.kpis()
        if tool == "top_n":
            return self.svc.top_n(args["dimension"], args.get("metric", "revenue"),
                                  args.get("n", 5), args.get("ascending", False))
        if tool == "sql_query":
            return self.svc.safe_query(args["sql"])
        if tool == "forecast":
            return self.svc.forecast(int(args.get("horizon", 14)))
        if tool == "rfm_segments":
            return self.svc.segments()
        if tool == "churn_risk":
            return self.svc.churn_top(int(args.get("n", 5)))
        if tool == "search_knowledge":
            return self.svc.ask(args["question"], actor="agent")
        raise ValueError(f"Tool not allowed: {tool}")

    def _llm_plan(self, question: str) -> list[dict] | None:
        if not (self.llm and self.llm.enabled):
            return None
        text = self.llm.complete(
            "You plan tool calls for a retail analytics agent. Reply with ONLY a JSON list of "
            '{"tool": ..., "args": {...}} objects. Tools: kpi_summary(), top_n(dimension,metric,n), '
            "forecast(horizon), rfm_segments(), churn_risk(n), search_knowledge(question). "
            f"dimension in {sorted(DIMENSIONS)}, metric in {sorted(METRICS)}. At most {self.max_steps} steps.",
            question, max_tokens=300)
        try:
            return validate_plan(json.loads(text)) if text else None
        except (ValueError, TypeError):
            return None

    def stream(self, question: str, actor: str = "agent"):
        """Generator of events: plan -> step (one per tool, as soon as it finishes) -> final."""
        question = question.strip()[:500]
        p = plan(question)
        if not p["refusal"]:
            llm_steps = self._llm_plan(question)
            if llm_steps:
                p["steps"] = llm_steps
        if self.ledger:
            self.ledger.append(actor, "agent_plan", {"question": question, "refused": bool(p["refusal"]),
                                                     "tools": [s["tool"] for s in p["steps"]],
                                                     "flags": p.get("flags", [])})
        if p["refusal"]:
            yield {"type": "final", "answer": p["refusal"], "refused": True, "steps": [], "sources": []}
            return

        steps = p["steps"][: self.max_steps]
        yield {"type": "plan", "tools": [s["tool"] for s in steps]}
        trace, parts, sources = [], [], []
        for step in steps:
            t0 = time.monotonic()
            try:
                obs = self._run_tool(step["tool"], step["args"])
                ok, text = True, self._render(step["tool"], step["args"], obs)
                if step["tool"] == "search_knowledge":
                    sources = obs.get("sources", [])
            except (SQLGuardError, ValueError, KeyError, FileNotFoundError) as e:
                ok, text = False, f"{step['tool']} failed: {e}"
            entry = {"tool": step["tool"], "args": {k: v for k, v in step["args"].items() if k != "sql"} |
                     ({"sql": step["args"]["sql"][:200]} if "sql" in step["args"] else {}),
                     "ok": ok, "ms": round((time.monotonic() - t0) * 1000, 1)}
            trace.append(entry)
            parts.append(text)
            if self.ledger:
                self.ledger.append(actor, "agent_tool", {"tool": step["tool"], "ok": ok})
            yield {"type": "step", **entry, "text": mask_pii(text)}
        yield {"type": "final", "answer": mask_pii("\n\n".join(parts)), "refused": False,
               "steps": trace, "sources": sources}

    def run(self, question: str, actor: str = "agent") -> dict:
        final = None
        for event in self.stream(question, actor):
            final = event
        return {k: v for k, v in final.items() if k != "type"}

    # ---- rendering
    @staticmethod
    def _render(tool: str, args: dict, obs) -> str:
        if tool == "kpi_summary":
            return (f"Overall: net revenue {inr(obs['net_revenue'])}, profit {inr(obs['net_profit'])} "
                    f"({obs['profit_margin_pct']}% margin), {obs['orders']:,} orders from {obs['customers']:,} "
                    f"customers, AOV {inr(obs['avg_order_value'])}, return rate {obs['return_rate_pct']}% "
                    f"({obs['first_date']} to {obs['last_date']}).")
        if tool in ("top_n", "sql_query"):
            cols, rows = obs["columns"], obs["rows"]
            if tool == "top_n":
                metric = args.get("metric", "revenue")
                plural = {"category": "categories", "city": "cities", "age_band": "age bands"}.get(
                    args["dimension"], args["dimension"] + "s")
                head = f"{'Bottom' if args.get('ascending') else 'Top'} {len(rows)} {plural} by {metric}:"
                fmt = (lambda v: inr(v)) if metric in MONEY_METRICS else (lambda v: f"{v:,}")
                lines = [f"{i}. {r[0]}: {fmt(r[1])}" + ("%" if metric == "margin" else "") for i, r in enumerate(rows, 1)]
                return head + "\n" + "\n".join(lines)
            lines = [" | ".join(cols)] + [" | ".join(str(v) for v in r) for r in rows[:10]]
            more = f"\n(showing 10 of {obs['row_count']}{'+' if obs['truncated'] else ''} rows)" if obs["row_count"] > 10 else ""
            return "Query result:\n" + "\n".join(lines) + more
        if tool == "forecast":
            rows = obs["rows"]
            total = sum(r["forecast"] for r in rows)
            return (f"Forecast for the next {len(rows)} days: about {inr(total)} net revenue "
                    f"(daily average {inr(total / len(rows))}; band {inr(sum(r['lower'] for r in rows))} to "
                    f"{inr(sum(r['upper'] for r in rows))}). Based on a gradient-boosting model, weekly WAPE "
                    f"{obs['backtest_wape_weekly_pct']}% in backtest.")
        if tool == "rfm_segments":
            lines = [f"- {r['segment']}: {r['customers']:,} customers ({r['customer_share_pct']}%)" for r in obs["rows"]]
            return "RFM segments:\n" + "\n".join(lines)
        if tool == "churn_risk":
            lines = [f"- customer {r['customer_key']}: churn risk {r['churn_risk']:.0%}, value at risk {inr(r['value_at_risk'])}"
                     for r in obs["rows"]]
            return "Highest value-at-risk customers (anonymous keys only):\n" + "\n".join(lines)
        if tool == "search_knowledge":
            return obs["answer"]
        return str(obs)
