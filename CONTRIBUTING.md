# Contributing

```bash
pip install -r requirements-dev.txt
python -m retailpulse.cli run-all --quick   # small synthetic dataset
python -m pytest -q
python -m retailpulse.cli serve --port 8000 # UI at http://127.0.0.1:8000
```

Rules of the road
- Every figure shown in the UI must come from the SQL warehouse or a model output, never hard-coded.
- Server data is rendered with `textContent` only (no `innerHTML`); the CSP forbids inline script/style.
- New endpoints use the `route()` decorator so they appear in OpenAPI and get role checks.
- Security-relevant changes need a test (see `tests/test_security.py`).
- Never commit `.env`, API keys or generated `data/`.
