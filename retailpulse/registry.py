"""Tiny model registry: versioned entries with data fingerprint, parameters, metrics and promotion gates.

(The same idea as MLflow's registry, kept as one auditable JSON file so the project has no extra service.)
"""
from __future__ import annotations

import hashlib
import json
import os
from datetime import datetime, timezone
from pathlib import Path

KEEP = 30


def fingerprint(*files: Path) -> str:
    h = hashlib.sha256()
    for f in files:
        h.update(Path(f).name.encode())
        h.update(Path(f).read_bytes())
    return h.hexdigest()[:16]


def _read(path: Path) -> list[dict]:
    try:
        return json.loads(Path(path).read_text(encoding="utf-8"))
    except (FileNotFoundError, ValueError):
        return []


def register(path: Path, model: str, params: dict, metrics: dict, data_fp: str, gates: dict[str, bool]) -> dict:
    now = datetime.now(timezone.utc)
    vid = hashlib.sha256(json.dumps([model, params, data_fp], sort_keys=True, default=str).encode()).hexdigest()[:8]
    entry = {
        "model": model,
        "version": f"{now:%Y%m%d-%H%M%S}-{vid}",
        "registered_at": now.isoformat(timespec="seconds"),
        "data_fingerprint": data_fp,
        "params": params,
        "metrics": metrics,
        "gates": gates,
        "promoted": all(gates.values()),
    }
    entries = (_read(path) + [entry])[-KEEP:]
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(".tmp")
    tmp.write_text(json.dumps(entries, indent=2, default=str), encoding="utf-8")
    os.replace(tmp, path)  # atomic
    return entry


def load(path: Path) -> list[dict]:
    return _read(path)


def latest_by_model(path: Path) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for e in _read(path):
        out[e["model"]] = e
    return out
