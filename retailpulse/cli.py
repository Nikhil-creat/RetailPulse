"""Command line: python -m retailpulse.cli <command>"""
from __future__ import annotations

import argparse
import json
import sys

from .config import Paths


def _service():
    from .service import RetailPulseService
    return RetailPulseService(Paths.default())


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="retailpulse", description="RetailPulse analytics + guarded AI")
    sub = p.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("run-all", help="generate data, build warehouse, train models, write reports")
    r.add_argument("--quick", action="store_true", help="small dataset (fast)")
    r.add_argument("--seed", type=int, default=None)
    a = sub.add_parser("ask", help="grounded Q&A (RAG)")
    a.add_argument("question")
    g = sub.add_parser("agent", help="tool-using analytics agent")
    g.add_argument("question")
    s = sub.add_parser("serve", help="start the secured API")
    s.add_argument("--host", default="127.0.0.1")
    s.add_argument("--port", type=int, default=8000)
    s.add_argument("--no-bootstrap", action="store_true", help="don't build data if the warehouse is missing")
    k = sub.add_parser("make-key", help="create an API key (prints it once) and its hash for RP_API_KEYS")
    k.add_argument("--name", default="default")
    k.add_argument("--role", default="analyst", choices=["viewer", "analyst", "admin"])
    sub.add_parser("verify-audit", help="verify the tamper-evident audit log")
    sub.add_parser("eval", help="run RAG + agent evaluation suites")
    e = sub.add_parser("export-static", help="export a static read-only demo (GitHub Pages) from the real pipeline outputs")
    e.add_argument("--out", default="site")
    t = sub.add_parser("train-cnn", help="train the PyTorch CNN (needs torch)")
    t.add_argument("--epochs", type=int, default=8)
    args = p.parse_args(argv)

    if args.cmd == "run-all":
        from .pipeline import run_all
        run_all(Paths.default(), quick=args.quick, seed=args.seed)
    elif args.cmd == "ask":
        out = _service().ask(args.question, actor="cli")
        print(out["answer"])
        for src in out["sources"]:
            print(f"  [{src['n']}] {src['title']} (score {src['score']})")
    elif args.cmd == "agent":
        out = _service().run_agent(args.question, actor="cli")
        print(out["answer"])
        print("\nsteps:", json.dumps(out["steps"]))
    elif args.cmd == "serve":
        paths = Paths.default()
        if not paths.db_path.exists() and not args.no_bootstrap:
            from .pipeline import run_all
            print("Warehouse not found; building it first (one-off)...", flush=True)
            run_all(paths, quick=False)
        import uvicorn
        uvicorn.run("retailpulse.api:app", host=args.host, port=args.port, log_level="info")
    elif args.cmd == "make-key":
        from .security import generate_api_key
        key, digest = generate_api_key()
        print("API key (shown once, store it in a password manager):\n  " + key)
        print(f"\nAdd this to RP_API_KEYS in your .env (it holds only the hash; separate several keys with commas):\n  {args.name}:{digest}:{args.role}")
    elif args.cmd == "verify-audit":
        from .security import AuditLedger
        ok, bad = AuditLedger(Paths.default().audit_log).verify()
        print("audit log OK" if ok else f"TAMPERING DETECTED at line {bad}")
        return 0 if ok else 1
    elif args.cmd == "eval":
        from . import evals, rag
        kb = rag.KnowledgeBase.load(Paths.default().kb_path)
        print(json.dumps({"rag": rag.eval_retrieval(kb, evals.RAG_CASES), "agent": evals.eval_agent_plans()}, indent=2))
    elif args.cmd == "export-static":
        from .export_static import export
        print(json.dumps(export(args.out), indent=2))
    elif args.cmd == "train-cnn":
        from .vision import cnn_torch
        print(json.dumps(cnn_torch.train_cnn(Paths.default().models_dir, epochs=args.epochs), indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
