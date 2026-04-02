# SYSU JWXT Agent

[English](./README.md) | [简体中文](./README.zh-CN.md)

Local service and agent-facing tooling for reading data from the SYSU teaching affairs system (`jwxt.sysu.edu.cn`) using an authorized student session.

## Scope

- Only reads data the signed-in user is already allowed to access.
- `v1` supports timetable, exams, grades, empty-classroom, and CET score queries.
- Authentication is handled through normal `NetID/CAS` flows, with manual takeover allowed when automation cannot complete login.

## Architecture

- `FastAPI` exposes a local REST API for agent consumption.
- `Playwright` handles browser-backed authentication and session reuse.
- A typed client layer hides upstream page/API details from the REST layer.
- Timetable responses are normalized and cached locally as a fallback when real-time fetch fails.
- A keepalive worker can periodically probe session validity to reduce session expiry impact.

## API

- `GET /health`: service health.
- `POST /auth/login`: start or refresh login flow.
- `POST /auth/refresh`: force session refresh.
- `POST /auth/import-state`: import browser storage state or cookie list.
- `GET /auth/keepalive/status`: get keepalive worker status and counters.
- `POST /auth/keepalive/start|stop|ping`: control keepalive worker.
- `GET /timetable?term=current&week=11`: fetch normalized timetable for a term/week.
- `GET /exams?term=2025-1&exam_week_type=18-19周期末考`: fetch exam info.
- `GET /grades?term=2025-1`: fetch grade list and summary.
- `GET /classrooms/empty?date=2026-04-03&campus=东校园&section_range=1-4`: fetch empty classrooms for required section range.
- `GET /cet-scores?level=4|6`: fetch CET-4/CET-6 scores.

## Agent-Facing Output Notes

- Most endpoints support `include_raw=true` for troubleshooting and schema evolution.
- `/classrooms/empty` enforces three required filters (`date`, `campus`, `section_range`) to avoid oversized result sets.
- `/cet-scores` defaults to a compact schema suitable for planning and analysis:
  - `score`, `exam_year`, `half_year`, `subject`
  - section scores (`hearing_score`, `reading_score`, `writing_score`)
  - status flags (`missing_test`, `violation`)

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

Session monitor helper (logs once per minute by default):

```bash
.venv/bin/python scripts/session_validity_monitor.py
```

Useful options:

```bash
.venv/bin/python scripts/session_validity_monitor.py --interval-seconds 60 --output data/monitor/session-validity.log
```

## Notes

- Credentials are intentionally not persisted by default.
- Session state is stored under `data/` and should be treated as sensitive.
- Upstream selectors and API contracts are expected to change; parsing code fails loudly instead of silently returning empty data.
- If upstream APIs return unexpected structures, prefer preserving `raw` payloads and updating parsers explicitly.
