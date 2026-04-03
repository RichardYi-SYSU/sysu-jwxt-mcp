# Agent Guide

## Purpose

This repository exists to give an agent a safe, local way to read teaching-affairs data from `jwxt.sysu.edu.cn` for one authorized user.

It now exposes the same capabilities through both a REST API and a local `stdio` MCP server.

## Guardrails

- Do not implement authentication bypasses or attempt to access data outside the signed-in user's scope.
- Treat cookies, storage state, and local cache as sensitive.
- When upstream pages or APIs change, fail explicitly instead of guessing.
- Prefer browser-observed authenticated APIs over brittle scraping when both are available.

## Operator Workflow

1. Start the local API service.
2. Prefer QR login for the student flow:
   - `POST /auth/qr/start`
   - show `qr_ascii` or `qr_png_path`
   - poll `GET /auth/qr/status` until `success`
3. Use `POST /auth/import-state` only as a fallback when QR automation cannot complete login.
4. Start keepalive (`POST /auth/keepalive/start`) and verify status (`GET /auth/keepalive/status`).
5. Call data endpoints as needed:
   - `GET /timetable`
   - `GET /exams`
   - `GET /grades`
   - `GET /classrooms/empty`
   - `GET /cet-scores`
6. If real-time fetch fails, inspect explicit error code (`unauthenticated`, `invalid_query`, `upstream_not_implemented`) before retrying.

For MCP-based clients, use the mirrored tools instead of the REST endpoints:

- `auth_refresh`
- `auth_qr_start|status|confirm`
- `auth_keepalive_status|start|stop|ping`
- `get_timetable`
- `get_exams`
- `get_grades`
- `get_empty_classrooms`
- `get_cet_scores`

## Expected Next Steps

- Keep refining upstream parsers with `include_raw=true` payload samples.
- Add narrow response models for remaining pages (training plan, notices, seat assignment).
- Keep endpoint contracts strict (required filters for high-cardinality queries).
- Preserve the verified QR-login assumption that student SSO must go through `pattern=student-login`.
