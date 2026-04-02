# Agent Guide

## Purpose

This repository exists to give an agent a safe, local way to read teaching-affairs data from `jwxt.sysu.edu.cn` for one authorized user.

## Guardrails

- Do not implement authentication bypasses or attempt to access data outside the signed-in user's scope.
- Treat cookies, storage state, and local cache as sensitive.
- When upstream pages or APIs change, fail explicitly instead of guessing.
- Prefer browser-observed authenticated APIs over brittle scraping when both are available.

## Operator Workflow

1. Start the local API service.
2. Import or refresh session state (`POST /auth/import-state` or `POST /auth/login`).
3. Start keepalive (`POST /auth/keepalive/start`) and verify status (`GET /auth/keepalive/status`).
4. Call data endpoints as needed:
   - `GET /timetable`
   - `GET /exams`
   - `GET /grades`
   - `GET /classrooms/empty`
   - `GET /cet-scores`
5. If real-time fetch fails, inspect explicit error code (`unauthenticated`, `invalid_query`, `upstream_not_implemented`) before retrying.

## Expected Next Steps

- Keep refining upstream parsers with `include_raw=true` payload samples.
- Add narrow response models for remaining pages (training plan, notices, seat assignment).
- Keep endpoint contracts strict (required filters for high-cardinality queries).
