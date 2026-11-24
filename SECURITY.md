# Security Policy

## Controls Implemented
- **Role-Based Access Control (RBAC):** `viewer < analyst < admin`
- **SQL & Prompt Injection Defense:** Read-only query allowlisting, mutating keyword rejection (`DROP`, `DELETE`, `UPDATE`, `INSERT`, `sqlite_master`), and retrieved-chunk isolation.
- **API Key Hygiene:** Keys are read from environment variables (`GROQ_API_KEY`, `GEMINI_API_KEY`), transmitted only via headers (`Authorization` / `x-goog-api-key`), and never committed or exposed in static exports.
- **Container Hardening:** Multi-stage Docker build with `web/` assets verified and non-root execution.

## Reporting a Vulnerability
Do not open public issues with exploit payloads or credentials. Contact the maintainer via GitHub Security Advisories (`Nikhil-creat/RetailPulse`).
