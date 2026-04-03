# MCP Integration

This repository ships a local `stdio` MCP server on top of the same JWXT services used by the compatibility REST API.

## Run the Server

```bash
uv sync
uv run playwright install chromium
uv run sysu-jwxt-mcp
```

## Recommended Client Configurations

All examples below use the same local command (avoid `bash -lc`; shell startup output can break MCP startup in some IDE integrations):

```bash
/path/to/sysu-jwxt-mcp/.venv/bin/sysu-jwxt-mcp
```

If you prefer `uv run`, sync once in advance (`uv sync`) so IDE startup does not depend on online package resolution.

### Codex

`~/.codex/config.toml`

```toml
[mcp_servers.sysu-jwxt]
command = "/path/to/sysu-jwxt-mcp/.venv/bin/sysu-jwxt-mcp"
```

### Claude Code

`.mcp.json`

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

`~/.cursor/mcp.json`

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

`~/.copilot/mcp-config.json`

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

## Tool Discovery Troubleshooting

If your IDE shows no tools, verify startup from a terminal first:

1. One-time setup:

```bash
uv sync
uv run playwright install chromium
```

2. Stdio handshake check:

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

If this fails, check path replacement, dependency installation, and whether shell wrappers print text before MCP initialization.

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

## Login Flow

### Terminal clients

1. Call `auth_qr_terminal`
2. Scan the ASCII QR code
3. Poll `auth_qr_status`
4. When `status=success`, call query tools

### GUI clients

1. Call `auth_qr_start`
2. Render the returned QR image inline in the chat or app session
3. Poll `auth_qr_status`
4. When `status=success`, call query tools

`qr_png_path` is a fallback field for debugging. GUI clients should not require users to open files from disk.

## Verification

After login, try one of:

- `get_grades(term="2025-1")`
- `get_timetable(term="2025-2", week=11)`
- `get_exams(term="2025-2", exam_week_type="18-19周期末考")`
- `get_empty_classrooms(date="2026-04-04", campus="东校园", section_range="1-4")`
- `get_cet_scores(level=4)`

## Common Errors

- `qr_session_not_found`
  The QR runtime lived in another MCP server process, or the session expired before polling.
- `unauthenticated`
  The login flow did not complete or the upstream session expired.
- `Playwright Sync API inside the asyncio loop`
  This is fixed in the MCP layer by dispatching blocking service calls to worker threads. Restart the MCP server after upgrading.
- `invalid_query`
  One of the query parameters does not match the strict JWXT adapter validation.

## Notes

- The verified student SSO path must use `pattern=student-login`.
- The MCP layer calls the service layer directly; it does not self-call the REST API.
- Blocking Playwright and HTTP work is dispatched off the MCP event loop so async MCP clients can call query tools safely.
