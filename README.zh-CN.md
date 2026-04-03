# SYSU JWXT Agent

[English](./README.md) | [简体中文](./README.zh-CN.md)

一个本地 `stdio` MCP 服务，用于在已授权学生会话下读取中大教务系统 `jwxt.sysu.edu.cn` 的数据。

当前仓库以本地 MCP server 为第一入口。REST API 仍然保留，但主要用于调试和兼容，不再是主使用路径。

## Quick Start

如果本机还没有安装 `uv`，先参考：

- <https://docs.astral.sh/uv/getting-started/installation/>

然后执行：

```bash
uv sync
uv run playwright install chromium
uv run sysu-jwxt-mcp
```

这会在当前项目目录启动本地 MCP 服务。

## MCP Server Configuration

统一使用下面这条本地启动命令：

```bash
bash -lc 'cd /path/to/sysu-jwxt-agent && uv run sysu-jwxt-mcp'
```

将 `/path/to/sysu-jwxt-agent` 替换成你本地仓库的实际路径。

### Codex

在 `~/.codex/config.toml` 中加入：

```toml
[mcp_servers.sysu-jwxt]
command = "bash"
args = ["-lc", "cd /path/to/sysu-jwxt-agent && uv run sysu-jwxt-mcp"]
```

### Claude Code

在项目根目录创建 `.mcp.json`：

```json
{
  "mcpServers": {
    "sysu-jwxt": {
      "command": "bash",
      "args": ["-lc", "cd /path/to/sysu-jwxt-agent && uv run sysu-jwxt-mcp"]
    }
  }
}
```

### Cursor

在 `~/.cursor/mcp.json` 中加入：

```json
{
  "mcpServers": {
    "sysu-jwxt": {
      "command": "bash",
      "args": ["-lc", "cd /path/to/sysu-jwxt-agent && uv run sysu-jwxt-mcp"]
    }
  }
}
```

### GitHub Copilot CLI

在 `~/.copilot/mcp-config.json` 中加入：

```json
{
  "mcpServers": {
    "sysu-jwxt": {
      "type": "stdio",
      "command": "bash",
      "args": ["-lc", "cd /path/to/sysu-jwxt-agent && uv run sysu-jwxt-mcp"],
      "tools": ["*"]
    }
  }
}
```

## 首次使用

### 终端型客户端

调用：

```text
auth_qr_terminal
```

它会返回：

- `login_session_id`
- 可扫码的 ASCII 二维码
- 下一步轮询提示

随后轮询：

```text
auth_qr_status(login_session_id="...")
```

### GUI 型客户端

调用：

```text
auth_qr_start
```

对于 GUI 集成，二维码应直接在会话里展示，优先渲染返回的图像内容，而不是要求用户去目录里打开一个 PNG 文件。只有客户端确实不支持内联图片时，才退回文件路径。

用同一个 `login_session_id` 轮询，直到 `status="success"`。

### 验证登录后的查询

扫码成功后，可直接调用：

```text
get_grades(term="2025-1")
get_timetable(term="2025-2", week=11)
get_exams(term="2025-2", exam_week_type="18-19周期末考")
get_empty_classrooms(date="2026-04-04", campus="东校园", section_range="1-4")
get_cet_scores(level=4)
```

## 核心 Tools

- `auth_refresh`：检查当前会话是否仍有效。
- `auth_qr_start`：面向 GUI 客户端的扫码登录入口。
- `auth_qr_terminal`：面向纯终端客户端的扫码登录入口。
- `auth_qr_status`：轮询登录状态，并在成功时自动落盘 `data/state/storage_state.json`。
- `auth_keepalive_status|start|stop|ping`：查看和控制保活。
- `get_timetable`：读取学期/周维度的标准化课表。
- `get_exams`：读取考试周和考试安排。
- `get_grades`：读取学期成绩、课程类型、绩点和排名。
- `get_empty_classrooms`：读取指定日期、校区、节次范围的空教室。
- `get_cet_scores`：读取四级或六级成绩。

## 仓库结构

- `src/sysu_jwxt_agent/`：MCP server、REST 兼容层和 JWXT service。
- `scripts/cli/`：用户向辅助脚本。
- `scripts/dev/`：逆向和探测脚本。
- `docs/mcp.md`：MCP 使用说明和各客户端补充说明。
- `docs/rest.md`：REST 兼容接口说明。
- `docs/dev/`：登录观测和逆向笔记。

## 进阶说明

REST 仍可用于调试和兼容：

- `uv run uvicorn sysu_jwxt_agent.main:app --reload`
- 具体接口说明见 `docs/rest.md`

用户向辅助脚本：

```bash
uv run python scripts/cli/qr_login_cli.py
uv run python scripts/cli/session_validity_monitor.py --interval-seconds 60
```

开发与逆向文档：

- `docs/mcp.md`
- `docs/rest.md`
- `docs/dev/login-observation.md`
- `docs/dev/live-discovery.md`
- `docs/dev/session-import.md`
- `docs/dev/implementation-plan.md`

## 备注

- `data/` 下的会话产物属于敏感信息。
- 当前已验证可用的学生登录链路必须走 `pattern=student-login`。
- 校区参数不接受 `东校` 这类简称，应使用 `东校园` 这类规范值。
- MCP 中所有阻塞型 Playwright 调用都已移出事件循环，异步客户端可以安全调用查询工具。
