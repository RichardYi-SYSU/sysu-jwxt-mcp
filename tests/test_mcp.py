import asyncio

import pytest
from mcp.types import CallToolResult

from sysu_jwxt_agent.bootstrap import AppServices
from sysu_jwxt_agent.mcp_server import build_mcp_server
from sysu_jwxt_agent.schemas import (
    CetScoresResponse,
    EmptyClassroomsResponse,
    GradesResponse,
    KeepaliveStatus,
    QrLoginConfirmResponse,
    QrLoginStartResponse,
    QrLoginStatusResponse,
    SessionStatus,
    TimetableResponse,
)
from sysu_jwxt_agent.services.jwxt import AuthenticationRequiredError


class StubAuthService:
    def refresh(self) -> SessionStatus:
        return SessionStatus(
            authenticated=True,
            message="ok",
            upstream_code=200,
        )

    def start_qr_login(self) -> QrLoginStartResponse:
        return QrLoginStartResponse(
            login_session_id="abc12345",
            status="pending",
            qr_image_base64="ZmFrZQ==",
            qr_ascii="QR",
            qr_png_path="data/state/qr-login/abc12345.png",
            expires_at="2026-04-03T00:00:00+00:00",
            message="ok",
        )

    def get_qr_login_status(self, login_session_id: str) -> QrLoginStatusResponse:
        return QrLoginStatusResponse(
            login_session_id=login_session_id,
            status="success",
            authenticated=True,
            state_persisted=True,
            state_path="data/state/storage_state.json",
            cookie_count=7,
            message="persisted",
        )

    def confirm_qr_login(self, login_session_id: str) -> QrLoginConfirmResponse:
        return QrLoginConfirmResponse(
            login_session_id=login_session_id,
            status="success",
            authenticated=True,
            imported=True,
            cookie_count=7,
            state_path="data/state/storage_state.json",
            message="persisted",
        )


class StubKeepaliveService:
    def status(self) -> KeepaliveStatus:
        return KeepaliveStatus(enabled=True, interval_seconds=300, running=False)

    def start(self) -> KeepaliveStatus:
        return KeepaliveStatus(enabled=True, interval_seconds=300, running=True)

    def stop(self) -> KeepaliveStatus:
        return KeepaliveStatus(enabled=True, interval_seconds=300, running=False)

    def ping_once(self) -> KeepaliveStatus:
        return KeepaliveStatus(
            enabled=True,
            interval_seconds=300,
            running=False,
            authenticated=True,
            last_ok=True,
        )


class StubJwxtClient:
    def __init__(self, authenticated: bool = True) -> None:
        self._authenticated = authenticated

    def get_timetable(self, term: str, week: int | None = None, include_raw: bool = False) -> TimetableResponse:
        if not self._authenticated:
            raise AuthenticationRequiredError("No authenticated session is available.")
        return TimetableResponse(
            term=term,
            week=week,
            stale=False,
            source="live",
            entries=[],
        )

    def get_grades(self, term: str, include_raw: bool = False) -> GradesResponse:
        if not self._authenticated:
            raise AuthenticationRequiredError("No authenticated session is available.")
        return GradesResponse(
            term=term,
            stale=False,
            source="live",
            entries=[
                {
                    "term": term,
                    "course_name": "操作系统原理",
                    "course_type": "专必",
                    "credit": 3.0,
                    "score": "95",
                    "grade_point": 4.5,
                    "rank": "1/60",
                }
            ],
        )

    def get_exams(self, term: str, exam_week_id=None, exam_week_type=None, include_raw: bool = False):
        raise NotImplementedError

    def get_empty_classrooms(
        self,
        *,
        date_value: str,
        campus: str,
        section_range: str,
        include_raw: bool = False,
    ) -> EmptyClassroomsResponse:
        if not self._authenticated:
            raise AuthenticationRequiredError("No authenticated session is available.")
        return EmptyClassroomsResponse(
            date=date_value,
            campus=campus,
            campus_id="5063559",
            section_range=section_range,
            stale=False,
            source="live",
            entries=[],
        )

    def get_cet_scores(self, *, level: int, include_raw: bool = False) -> CetScoresResponse:
        if not self._authenticated:
            raise AuthenticationRequiredError("No authenticated session is available.")
        return CetScoresResponse(level=level, stale=False, source="live", entries=[])


def _build_stub_server(authenticated: bool = True):
    services = AppServices(
        browser_manager=None,  # type: ignore[arg-type]
        auth_service=StubAuthService(),  # type: ignore[arg-type]
        keepalive_service=StubKeepaliveService(),  # type: ignore[arg-type]
        cache=None,  # type: ignore[arg-type]
        jwxt_client=StubJwxtClient(authenticated=authenticated),  # type: ignore[arg-type]
    )
    return build_mcp_server(services=services)


def _structured_result(result):
    if isinstance(result, CallToolResult):
        return result.structuredContent
    assert isinstance(result, tuple)
    assert len(result) == 2
    return result[1]


def test_mcp_lists_expected_tools() -> None:
    server = _build_stub_server()

    tools = asyncio.run(server.list_tools())
    names = {tool.name for tool in tools}

    assert "auth_refresh" in names
    assert "auth_qr_start" in names
    assert "auth_qr_terminal" in names
    assert "get_timetable" in names
    assert "get_grades" in names
    assert "get_empty_classrooms" in names
    assert "get_cet_scores" in names


def test_mcp_auth_qr_start_hides_base64_by_default() -> None:
    server = _build_stub_server()

    result = asyncio.run(server.call_tool("auth_qr_start", {}))
    structured = _structured_result(result)

    assert structured["login_session_id"] == "abc12345"
    assert "qr_image_base64" not in structured
    assert structured["qr_ascii"] == "QR"
    assert isinstance(result, CallToolResult)
    assert len(result.content) == 2
    assert result.content[0].type == "text"
    assert result.content[1].type == "image"


def test_mcp_auth_qr_start_can_include_base64() -> None:
    server = _build_stub_server()

    result = _structured_result(asyncio.run(server.call_tool("auth_qr_start", {"include_base64": True})))

    assert result["qr_image_base64"] == "ZmFrZQ=="


def test_mcp_auth_qr_terminal_returns_plain_text_view() -> None:
    server = _build_stub_server()

    content, result = asyncio.run(server.call_tool("auth_qr_terminal", {}))

    assert len(content) == 1
    assert "login_session_id: abc12345" in content[0].text
    assert "status: pending" in content[0].text
    assert "qr_png_path: data/state/qr-login/abc12345.png" in content[0].text
    assert "\nQR\n" in content[0].text
    assert result["result"] == content[0].text


def test_mcp_get_grades_returns_structured_payload() -> None:
    server = _build_stub_server()

    result = _structured_result(asyncio.run(server.call_tool("get_grades", {"term": "2025-1"})))

    assert result["term"] == "2025-1"
    assert result["entries"][0]["course_name"] == "操作系统原理"
    assert result["entries"][0]["rank"] == "1/60"


def test_mcp_query_tool_surfaces_unauthenticated_errors() -> None:
    server = _build_stub_server(authenticated=False)

    with pytest.raises(Exception, match="unauthenticated: No authenticated session is available."):
        asyncio.run(server.call_tool("get_timetable", {"term": "2025-2", "week": 11}))
