# MCP Integration

## Summary

This repository now exposes a local `stdio` MCP server on top of the same JWXT services used by the REST API.

- Transport: `stdio`
- Server entrypoint: `sysu-jwxt-mcp`
- Implementation: `src/sysu_jwxt_agent/mcp_server.py`
- Shared runtime bootstrap: `src/sysu_jwxt_agent/bootstrap.py`

The MCP layer does not self-call the REST API. It reuses `AuthService`, `JwxtClient`, and `SessionKeepaliveService` directly.

## Available Tools

- `auth_refresh`
- `auth_qr_start`
- `auth_qr_terminal`
- `auth_qr_status`
- `auth_qr_confirm`
- `auth_keepalive_status`
- `auth_keepalive_start`
- `auth_keepalive_stop`
- `auth_keepalive_ping`
- `get_timetable`
- `get_exams`
- `get_grades`
- `get_empty_classrooms`
- `get_cet_scores`

## Run Locally

```bash
source .venv/bin/activate
sysu-jwxt-mcp
```

Equivalent:

```bash
python -m sysu_jwxt_agent.mcp_server
```

## Recommended Login Flow

1. In CLI-oriented clients such as Codex CLI, call `auth_qr_terminal`
2. In structured clients, call `auth_qr_start` and render `qr_ascii` or show `qr_png_path`
3. Poll `auth_qr_status`
4. When `status=success`, `data/state/storage_state.json` is already persisted
5. Then call query tools such as `get_grades` or `get_timetable`

Important:

- The verified student QR flow depends on `pattern=student-login` in the JWXT CAS entry.
- `auth_qr_start` hides `qr_image_base64` by default to keep stdio output compact.
- `auth_qr_terminal` returns a single plain-text block so terminal MCP clients can display the QR directly.
- MCP query tools run their blocking service calls in worker threads so `playwright.sync_api` does not execute inside the MCP event loop.
- `get_empty_classrooms` expects canonical campus names such as `东校园`.

## Client Notes

- Claude Desktop / Claude Code / Codex local workflows: use `stdio`
- OpenAI Agents SDK: first use `stdio`; add `streamable-http` in a later iteration if remote deployment is needed
- GitHub Copilot CLI: use the local `stdio` server command
