# REST Compatibility API

The repository is organized around the local MCP server. The REST API remains available for debugging, integration experiments, and backward compatibility.

## Run

```bash
uv sync
uv run uvicorn sysu_jwxt_agent.main:app --reload
```

## Endpoints

- `GET /health`
- `POST /auth/login`
- `POST /auth/refresh`
- `POST /auth/import-state`
- `POST /auth/qr/start`
- `GET /auth/qr/status`
- `POST /auth/qr/confirm`
- `GET /auth/keepalive/status`
- `POST /auth/keepalive/start`
- `POST /auth/keepalive/stop`
- `POST /auth/keepalive/ping`
- `GET /timetable`
- `GET /exams`
- `GET /grades`
- `GET /classrooms/empty`
- `GET /cet-scores`

## Examples

```bash
curl -sS -X POST http://127.0.0.1:8000/auth/refresh
curl -sS 'http://127.0.0.1:8000/grades?term=2025-1'
curl -sS 'http://127.0.0.1:8000/timetable?term=2025-2&week=11'
curl -sS 'http://127.0.0.1:8000/classrooms/empty?date=2026-04-04&campus=东校园&section_range=1-4'
```

## Notes

- `POST /auth/qr/start` returns both image and text-friendly QR fields.
- GUI frontends should render the QR directly from the returned image payload instead of asking users to browse to `qr_png_path`.
- `GET /classrooms/empty` requires `date`, `campus`, and `section_range`.
- `GET /cet-scores` requires `level=4` or `level=6`.
