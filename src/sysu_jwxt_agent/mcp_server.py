from __future__ import annotations

import asyncio
from typing import Any

from mcp.server.fastmcp import FastMCP

from sysu_jwxt_agent.bootstrap import AppServices, create_services
from sysu_jwxt_agent.config import settings
from sysu_jwxt_agent.services.auth import (
    QrLoginNotReadyError,
    QrLoginSessionNotFoundError,
    QrLoginStartError,
)
from sysu_jwxt_agent.services.jwxt import (
    AuthenticationRequiredError,
    InvalidQueryError,
    UpstreamNotImplementedError,
)


def _dump_model(model: Any) -> dict[str, Any]:
    return model.model_dump(exclude_none=True)


def _tool_error(code: str, message: str) -> RuntimeError:
    return RuntimeError(f"{code}: {message}")


def build_mcp_server(services: AppServices | None = None) -> FastMCP:
    services = services or create_services()
    auth_service = services.auth_service
    keepalive_service = services.keepalive_service
    jwxt_client = services.jwxt_client

    mcp = FastMCP(
        name="SYSU JWXT Agent",
        instructions=(
            "Use these tools to access teaching-affairs data for the currently authorized SYSU user. "
            "If the session is not authenticated, start QR login, poll status until success, and then retry."
        ),
        dependencies=["playwright", "fastapi", "httpx"],
        host=settings.host,
        port=settings.port,
    )

    @mcp.tool(
        name="auth_refresh",
        description="Check whether the current SYSU JWXT session is authenticated.",
        structured_output=True,
    )
    async def auth_refresh() -> dict[str, Any]:
        return _dump_model(await asyncio.to_thread(auth_service.refresh))

    @mcp.tool(
        name="auth_qr_start",
        description=(
            "Start student QR login and return a terminal-friendly QR payload. "
            "Use include_base64 only when the client needs the raw image data."
        ),
        structured_output=True,
    )
    async def auth_qr_start(include_base64: bool = False) -> dict[str, Any]:
        try:
            payload = _dump_model(await asyncio.to_thread(auth_service.start_qr_login))
        except QrLoginStartError as exc:
            raise _tool_error("qr_start_failed", str(exc)) from exc
        if not include_base64:
            payload.pop("qr_image_base64", None)
        return payload

    @mcp.tool(
        name="auth_qr_terminal",
        description=(
            "Start student QR login and return a plain-text terminal view with login_session_id "
            "and ASCII QR content. Use this when the client should display the QR directly in a CLI."
        ),
    )
    async def auth_qr_terminal() -> str:
        try:
            payload = await asyncio.to_thread(auth_service.start_qr_login)
        except QrLoginStartError as exc:
            raise _tool_error("qr_start_failed", str(exc)) from exc

        lines = [
            f"login_session_id: {payload.login_session_id}",
            f"status: {payload.status}",
        ]
        if payload.expires_at:
            lines.append(f"expires_at: {payload.expires_at}")
        if payload.qr_png_path:
            lines.append(f"qr_png_path: {payload.qr_png_path}")
        lines.append("")
        if payload.qr_ascii:
            lines.append(payload.qr_ascii)
        else:
            lines.append("qr_ascii unavailable")
            if payload.qr_png_path:
                lines.append(f"open png: {payload.qr_png_path}")
        lines.append("")
        lines.append("Poll auth_qr_status with the same login_session_id until status=success.")
        return "\n".join(lines)

    @mcp.tool(
        name="auth_qr_status",
        description="Poll QR login status. Success means storage_state.json has already been persisted.",
        structured_output=True,
    )
    async def auth_qr_status(login_session_id: str) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(
                auth_service.get_qr_login_status,
                login_session_id=login_session_id,
            )
            return _dump_model(result)
        except QrLoginSessionNotFoundError as exc:
            raise _tool_error("qr_session_not_found", str(exc)) from exc

    @mcp.tool(
        name="auth_qr_confirm",
        description="Compatibility endpoint for QR login. Returns the persisted success result and closes runtime state.",
        structured_output=True,
    )
    async def auth_qr_confirm(login_session_id: str) -> dict[str, Any]:
        try:
            result = await asyncio.to_thread(
                auth_service.confirm_qr_login,
                login_session_id=login_session_id,
            )
            return _dump_model(result)
        except QrLoginSessionNotFoundError as exc:
            raise _tool_error("qr_session_not_found", str(exc)) from exc
        except QrLoginNotReadyError as exc:
            raise _tool_error("qr_login_not_ready", str(exc)) from exc

    @mcp.tool(
        name="auth_keepalive_status",
        description="Get the JWXT session keepalive worker status.",
        structured_output=True,
    )
    async def auth_keepalive_status() -> dict[str, Any]:
        return _dump_model(await asyncio.to_thread(keepalive_service.status))

    @mcp.tool(
        name="auth_keepalive_start",
        description="Start the JWXT session keepalive worker.",
        structured_output=True,
    )
    async def auth_keepalive_start() -> dict[str, Any]:
        return _dump_model(await asyncio.to_thread(keepalive_service.start))

    @mcp.tool(
        name="auth_keepalive_stop",
        description="Stop the JWXT session keepalive worker.",
        structured_output=True,
    )
    async def auth_keepalive_stop() -> dict[str, Any]:
        return _dump_model(await asyncio.to_thread(keepalive_service.stop))

    @mcp.tool(
        name="auth_keepalive_ping",
        description="Run a single keepalive probe against the current session.",
        structured_output=True,
    )
    async def auth_keepalive_ping() -> dict[str, Any]:
        return _dump_model(await asyncio.to_thread(keepalive_service.ping_once))

    async def _call_query_tool(func, **kwargs: Any) -> dict[str, Any]:
        try:
            return _dump_model(await asyncio.to_thread(func, **kwargs))
        except AuthenticationRequiredError as exc:
            raise _tool_error("unauthenticated", str(exc)) from exc
        except InvalidQueryError as exc:
            raise _tool_error("invalid_query", str(exc)) from exc
        except UpstreamNotImplementedError as exc:
            raise _tool_error("upstream_not_implemented", str(exc)) from exc

    @mcp.tool(
        name="get_timetable",
        description="Get normalized timetable entries for a specific term and optional week.",
        structured_output=True,
    )
    async def get_timetable(
        term: str = "current",
        week: int | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        return await _call_query_tool(
            jwxt_client.get_timetable,
            term=term,
            week=week,
            include_raw=include_raw,
        )

    @mcp.tool(
        name="get_exams",
        description="Get exam info for a term, optionally filtered by exam week id or exam week type.",
        structured_output=True,
    )
    async def get_exams(
        term: str = "current",
        exam_week_id: str | None = None,
        exam_week_type: str | None = None,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        return await _call_query_tool(
            jwxt_client.get_exams,
            term=term,
            exam_week_id=exam_week_id,
            exam_week_type=exam_week_type,
            include_raw=include_raw,
        )

    @mcp.tool(
        name="get_grades",
        description="Get course grades and summary for a specific term.",
        structured_output=True,
    )
    async def get_grades(term: str = "current", include_raw: bool = False) -> dict[str, Any]:
        return await _call_query_tool(
            jwxt_client.get_grades,
            term=term,
            include_raw=include_raw,
        )

    @mcp.tool(
        name="get_empty_classrooms",
        description=(
            "Get empty classrooms for a specific date, canonical campus name, and section range. "
            "Use canonical campus names such as 东校园."
        ),
        structured_output=True,
    )
    async def get_empty_classrooms(
        date: str,
        campus: str,
        section_range: str,
        include_raw: bool = False,
    ) -> dict[str, Any]:
        return await _call_query_tool(
            jwxt_client.get_empty_classrooms,
            date_value=date,
            campus=campus,
            section_range=section_range,
            include_raw=include_raw,
        )

    @mcp.tool(
        name="get_cet_scores",
        description="Get CET-4 or CET-6 score records.",
        structured_output=True,
    )
    async def get_cet_scores(level: int, include_raw: bool = False) -> dict[str, Any]:
        return await _call_query_tool(
            jwxt_client.get_cet_scores,
            level=level,
            include_raw=include_raw,
        )

    return mcp


def main() -> None:
    build_mcp_server().run(transport="stdio")


if __name__ == "__main__":
    main()
