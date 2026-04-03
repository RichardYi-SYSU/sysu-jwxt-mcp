# SYSU JWXT Agent

[English](./README.md) | [简体中文](./README.zh-CN.md)

一个本地服务与 Agent 接口层，用于在已授权学生会话下读取中大教务系统（`jwxt.sysu.edu.cn`）数据。

当前仓库同时提供：

- 本地 REST API
- 复用同一套 JWXT service 层的本地 `stdio` MCP 服务

## 范围

- 仅读取当前登录用户本身有权限访问的数据。
- `v1` 已支持：课表、考试、成绩、空教室、四六级成绩查询。
- 鉴权沿用正常 `NetID/CAS` 登录流程。
- 学生端二维码登录现已完成端到端验证，扫码确认后可自动落盘 `data/state/storage_state.json`。
- 当自动化登录受限时，仍可退回 `import-state` 手动接管。

## 架构

- 使用 `FastAPI` 对外提供本地 REST API，供 Agent 调用。
- 使用 `Playwright` 处理浏览器态登录与会话复用。
- 通过类型化客户端层屏蔽上游页面/API 细节。
- 课表结果会做标准化并本地缓存，实时抓取失败时可回退缓存。
- 提供保活 worker 周期探测会话有效性，降低短会话过期影响。

## API

- `GET /health`: 服务健康检查。
- `POST /auth/login`: 启动或刷新登录流程。
- `POST /auth/refresh`: 强制刷新会话状态。
- `POST /auth/import-state`: 导入浏览器 storage state 或 cookie 列表。
- `POST /auth/qr/start`: 创建扫码登录会话，并返回二维码载荷（`qr_ascii`、`qr_png_path`、`qr_image_base64`）。
- `GET /auth/qr/status?login_session_id=...`: 轮询扫码状态，推进 CAS->JWXT SSO，并在成功后自动落盘 `storage_state.json`。
- `POST /auth/qr/confirm?login_session_id=...`: 兼容接口；返回已落盘的结果并关闭内存中的扫码会话。
- `GET /auth/keepalive/status`: 查看保活 worker 状态与计数器。
- `POST /auth/keepalive/start|stop|ping`: 控制保活 worker。
- `GET /timetable?term=current&week=11`: 查询指定学期/周课表（标准化输出）。
- `GET /exams?term=2025-1&exam_week_type=18-19周期末考`: 查询考试信息。
- `GET /grades?term=2025-1`: 查询成绩列表与汇总。
- `GET /classrooms/empty?date=2026-04-03&campus=东校园&section_range=1-4`: 查询指定节次范围空教室。
- `GET /cet-scores?level=4|6`: 查询四级/六级成绩。

## MCP

- 传输方式：本地 `stdio`
- 启动入口：`sysu-jwxt-mcp`
- tool 能力与当前鉴权/查询能力保持一致：
  - `auth_refresh`
  - `auth_qr_start|status|confirm`
  - `auth_qr_terminal`
  - `auth_keepalive_status|start|stop|ping`
  - `get_timetable`
  - `get_exams`
  - `get_grades`
  - `get_empty_classrooms`
  - `get_cet_scores`

使用方式与客户端接入说明见 `docs/mcp.md`。

## 面向 Agent 的输出约定

- 多数接口支持 `include_raw=true`，便于排障与上游字段演进。
- `/classrooms/empty` 强制要求 `date`、`campus`、`section_range` 三个过滤条件，避免结果集过大。
- `/cet-scores` 默认输出精简字段，便于规划和分析：
  - `score`, `exam_year`, `half_year`, `subject`
  - 分项成绩：`hearing_score`, `reading_score`, `writing_score`
  - 状态字段：`missing_test`, `violation`

## 扫码登录流程

1. 调用 `POST /auth/qr/start`。
2. 将返回的 `qr_ascii` 或 `qr_png_path` 展示给用户，用企业微信扫码并确认。
3. 轮询 `GET /auth/qr/status`。
4. 当状态为 `success` 时，`storage_state.json` 已经自动落盘。
5. `POST /auth/qr/confirm` 仅作为可选兼容接口，用于显式关闭内存中的扫码会话。

实现细节说明：

- 当前已验证可用的学生扫码链路必须走 `pattern=student-login` 的 JWXT CAS 入口。若使用不带 `pattern` 的裸 `/api/sso/cas/login`，会停在 CAS 已确认但 JWXT 未真正登录的状态。

## 开发

```bash
python -m venv .venv
source .venv/bin/activate
pip install -e .[dev]
playwright install chromium
uvicorn sysu_jwxt_agent.main:app --reload
```

进行真实 JWXT 联调前，可运行：

```bash
.venv/bin/python scripts/observe_login.py
```

脚本默认采用适合 SSH 的无头模式。仅当远端机器具备 GUI 时再使用 `--headed`。

登录观测与产物分析流程见 `docs/login-observation.md`。  
已验证的线上发现记录见 `docs/live-discovery.md`。  
纯 SSH 场景推荐登录路径见 `docs/session-import.md`。

会话监控小工具（默认每分钟记录一次）：

```bash
.venv/bin/python scripts/session_validity_monitor.py
```

常用参数示例：

```bash
.venv/bin/python scripts/session_validity_monitor.py --interval-seconds 60 --output data/monitor/session-validity.log
```

终端扫码辅助脚本（优先输出 ASCII 二维码，并自动轮询直到 `storage_state.json` 落盘）：

```bash
.venv/bin/python scripts/qr_login_cli.py
```

MCP 服务启动方式：

```bash
sysu-jwxt-mcp
```

对于 Codex CLI 这类终端型 MCP 客户端，优先使用纯文本二维码工具：

```text
调用 auth_qr_terminal
```

实现说明：

- `auth_qr_terminal` 会返回一整段纯文本，其中包含 `login_session_id`、`qr_png_path` 和 ASCII 二维码。
- MCP tools 会把阻塞型 service 调用派发到工作线程，避免在 MCP 的 asyncio 事件循环里直接运行同步版 Playwright。

扫码成功后的快速验证命令：

```bash
curl -sS -X POST http://127.0.0.1:8000/auth/refresh
curl -sS 'http://127.0.0.1:8000/grades?term=2025-1'
curl -sS 'http://127.0.0.1:8000/timetable?term=2025-2&week=11'
```

## 说明

- 默认不会持久化保存账号密码。
- 会话状态存放在 `data/` 目录，需按敏感数据处理。
- 上游选择器与接口结构可能变化；解析逻辑倾向于“显式失败”，避免静默返回空数据。
- 若上游返回结构异常，优先保留 `raw` 载荷并显式更新解析器。
- `/classrooms/empty` 目前要求使用规范校区名，例如 `东校园`；`东校` 这类简称会被参数校验拒绝。
