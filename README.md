# SYSU JWXT Agent

[English](./README.md) | [简体中文](./README.zh-CN.md)

Local MCP server for reading data from `jwxt.sysu.edu.cn` with an authorized student session.

This repository is organized around a local `stdio` MCP server. The REST API is still available for debugging and compatibility, but MCP is the primary entrypoint.

## Quick Start

Install `uv` first if it is not already available on your machine:

- <https://docs.astral.sh/uv/getting-started/installation/>

Then run:

```bash
uv sync
uv run playwright install chromium
uv run sysu-jwxt-mcp
```

That starts the local MCP server from the project root.

## MCP Server Configuration

Use the same local command everywhere (avoid `bash -lc`; some IDEs treat shell startup noise as MCP failure):

```bash
/path/to/sysu-jwxt-mcp/.venv/bin/sysu-jwxt-mcp
```

Replace `/path/to/sysu-jwxt-mcp` with your local checkout path.

If you prefer `uv run`, make sure dependencies are already synced first; otherwise `uv` may try to resolve packages online during IDE startup.

### Codex

Add this to `~/.codex/config.toml`:

```toml
[mcp_servers.sysu-jwxt]
command = "/path/to/sysu-jwxt-mcp/.venv/bin/sysu-jwxt-mcp"
```

### Claude Code

Create a project-level `.mcp.json`:

```json
{
  "mcpServers": {
    "sysu-jwxt": {
      "command": "/path/to/sysu-jwxt-mcp/.venv/bin/sysu-jwxt-mcp"
    }
  }
}
```

### Cursor

Add this to `~/.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "sysu-jwxt": {
      "command": "/path/to/sysu-jwxt-mcp/.venv/bin/sysu-jwxt-mcp"
    }
  }
}
```

### GitHub Copilot CLI

Add this to `~/.copilot/mcp-config.json`:

```json
{
  "mcpServers": {
    "sysu-jwxt": {
      "type": "stdio",
      "command": "/path/to/sysu-jwxt-mcp/.venv/bin/sysu-jwxt-mcp",
      "tools": ["*"]
    }
  }
}
```

### Tool discovery troubleshooting

If the IDE cannot see tools, verify these first:

1. Run one-time environment setup in the repo root:

   ```bash
   uv sync
   uv run playwright install chromium
   ```

2. Verify MCP tool discovery through stdio:

   ```bash
   python - <<'PY'
   import asyncio
   from mcp.client.session import ClientSession
   from mcp.client.stdio import stdio_client, StdioServerParameters

   async def main():
       server = StdioServerParameters(
           command="/path/to/sysu-jwxt-mcp/.venv/bin/sysu-jwxt-mcp",
       )
       async with stdio_client(server) as (r, w):
           async with ClientSession(r, w) as session:
               await session.initialize()
               tools = await session.list_tools()
               print([tool.name for tool in tools.tools])

   asyncio.run(main())
   PY
   ```

3. If initialization still fails, check for:
   - stale path (`/path/to/...` not replaced),
   - missing dependencies (run `uv sync` again),
   - shell wrappers that print to stdio before MCP starts.

## First Run

### Terminal clients

Call:

```text
auth_qr_terminal
```

This returns:

- `login_session_id`
- a terminal-safe ASCII QR code
- the next polling instruction

Then poll:

```text
auth_qr_status(login_session_id="...")
```

### GUI clients

Call:

```text
auth_qr_start
```

For GUI integrations, render the QR code directly in the chat session from the returned image payload. Do not require users to open a PNG file from disk unless the client cannot display inline images.

Poll with the same `login_session_id` until `status="success"`.

### Verify the session

After login succeeds, try one of:

```text
get_grades(term="2025-1")
get_timetable(term="2025-2", week=11)
get_exams(term="2025-2", exam_week_type="18-19周期末考")
get_empty_classrooms(date="2026-04-04", campus="东校园", section_range="1-4")
get_cet_scores(level=4)
```

## Core Tools

- `auth_refresh`: check whether the current session is authenticated.
- `auth_qr_start`: start QR login for GUI-capable clients.
- `auth_qr_terminal`: start QR login for terminal-only clients.
- `auth_qr_status`: poll login state and persist `data/state/storage_state.json` on success.
- `auth_keepalive_status|start|stop|ping`: inspect and control keepalive.
- `get_timetable`: read normalized timetable data for a term and optional week.
- `get_exams`: read exam week and exam entry data.
- `get_grades`: read term-scoped grades, course type, grade point, and rank.
- `get_empty_classrooms`: read empty classrooms for a required date, campus, and section range.
- `get_cet_scores`: read CET-4 or CET-6 scores.

## Repo Layout

- `src/sysu_jwxt_agent/`: MCP server, REST compatibility layer, and JWXT services.
- `scripts/cli/`: user-facing helper scripts.
- `scripts/dev/`: reverse-engineering and probing helpers.
- `docs/mcp.md`: MCP usage and client-specific notes.
- `docs/rest.md`: REST compatibility reference.
- `docs/dev/`: login observation and reverse-engineering notes.

## Advanced

REST remains available for debugging and compatibility:

- `uv run uvicorn sysu_jwxt_agent.main:app --reload`
- See `docs/rest.md` for endpoint reference.

User-facing helper scripts:

```bash
uv run python scripts/cli/qr_login_cli.py
uv run python scripts/cli/session_validity_monitor.py --interval-seconds 60
```

Development and reverse-engineering notes:

- `docs/mcp.md`
- `docs/rest.md`
- `docs/dev/login-observation.md`
- `docs/dev/live-discovery.md`
- `docs/dev/session-import.md`
- `docs/dev/implementation-plan.md`

## Notes

- Session artifacts under `data/` are sensitive.
- The verified student login path must go through `pattern=student-login`.
- Short campus aliases such as `东校` are not accepted; use canonical values such as `东校园`.
- Blocking Playwright work is dispatched off the MCP event loop so MCP query tools can be called safely from async clients.
