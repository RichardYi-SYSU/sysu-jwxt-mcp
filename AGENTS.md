# Agent Guide

## Purpose

This repository exists to give an agent a safe, local way to read teaching-affairs data from `jwxt.sysu.edu.cn` for one authorized user.

The primary entrypoint is a local `stdio` MCP server. The REST API remains available for debugging and compatibility.

## Guardrails

- Do not implement authentication bypasses or attempt to access data outside the signed-in user's scope.
- Treat cookies, storage state, and local cache as sensitive.
- When upstream pages or APIs change, fail explicitly instead of guessing.
- Prefer browser-observed authenticated APIs over brittle scraping when both are available.

## Operator Workflow

1. Start the local MCP server with `uv run sysu-jwxt-mcp`.
2. Prefer QR login for the student flow:
   - terminal clients: `auth_qr_terminal`
   - GUI clients: `auth_qr_start`
   - poll `auth_qr_status` until `success`
3. Use import-state only as a fallback when QR automation cannot complete login.
4. Start keepalive with `auth_keepalive_start` and verify with `auth_keepalive_status`.
5. Call data tools as needed:
   - `get_timetable`
   - `get_exams`
   - `get_grades`
   - `get_empty_classrooms`
   - `get_cet_scores`
6. If real-time fetch fails, inspect explicit error code (`unauthenticated`, `invalid_query`, `upstream_not_implemented`) before retrying.

For terminal clients, `auth_qr_terminal` is the preferred login tool because it renders a scanable ASCII QR code directly in the agent session.

For GUI clients, `auth_qr_start` should render the QR image inline in the client instead of asking the user to open `qr_png_path` manually.

Primary MCP tools:

- `auth_refresh`
- `auth_qr_start|terminal|status|confirm`
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
- Keep the repository MCP-first: README quick start, client config snippets, and `scripts/cli` should remain the primary user-facing surface.
