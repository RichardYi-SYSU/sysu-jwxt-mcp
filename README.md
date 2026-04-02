# SYSU JWXT Agent

Local service and agent-facing tooling for reading data from the SYSU teaching affairs system (`jwxt.sysu.edu.cn`) using an authorized student session.

## Scope

- Only reads data the signed-in user is already allowed to access.
- `v1` focuses on timetable reading.
- Authentication is handled through normal `NetID/CAS` flows, with manual takeover allowed when automation cannot complete login.

## Architecture

- `FastAPI` exposes a local REST API for agent consumption.
- `Playwright` handles browser-backed authentication and session reuse.
- A typed client layer hides upstream page/API details from the REST layer.
- Timetable responses are normalized and cached locally as a fallback when real-time fetch fails.

## API

- `GET /health`: service health.
- `POST /auth/login`: start or refresh login flow.
- `POST /auth/refresh`: force session refresh.
- `GET /timetable?term=current`: fetch normalized timetable for a term.

## Development

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
playwright install chromium
uvicorn sysu_jwxt_agent.main:app --reload
```

To prepare for real JWXT integration, run:

```bash
.venv/bin/python scripts/observe_login.py
```

This now defaults to a headless SSH-friendly mode. Use `--headed` only when the remote machine has GUI access.

See `docs/login-observation.md` for the artifact review workflow and headless limitations.
Concrete live findings are tracked in `docs/live-discovery.md`.
For SSH-only operation, the recommended login path is documented in `docs/session-import.md`.

## Notes

- Credentials are intentionally not persisted by default.
- Session state is stored under `data/` and should be treated as sensitive.
- Upstream selectors and API contracts are expected to change; parsing code fails loudly instead of silently returning empty data.
