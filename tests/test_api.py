from fastapi.testclient import TestClient
from unittest.mock import patch

from sysu_jwxt_agent.main import create_app
from sysu_jwxt_agent.schemas import ExamsResponse, TimetableResponse


def test_health() -> None:
    client = TestClient(create_app())

    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_timetable_requires_auth() -> None:
    client = TestClient(create_app())

    with patch(
        "sysu_jwxt_agent.services.auth.AuthService.is_authenticated",
        return_value=False,
    ):
        response = client.get("/timetable")

    assert response.status_code == 401
    assert response.json()["detail"]["code"] == "unauthenticated"


def test_login_reports_live_probe_when_unauthenticated() -> None:
    client = TestClient(create_app())

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService._probe_upstream_status", return_value={"code": 200, "data": 0}),
        patch(
            "sysu_jwxt_agent.services.auth.AuthService._fetch_cas_login_url",
            return_value="https://cas.sysu.edu.cn/esc-sso/login?service=example",
        ),
    ):
        response = client.post("/auth/login")

    assert response.status_code == 200
    assert response.json()["authenticated"] is False
    assert response.json()["login_required"] is True
    assert response.json()["cas_login_url"] == "https://cas.sysu.edu.cn/esc-sso/login?service=example"
    assert response.json()["upstream_code"] == 200


def test_import_state_writes_storage_state(tmp_path) -> None:
    from sysu_jwxt_agent.services.auth import AuthService
    from sysu_jwxt_agent.services.browser import BrowserLaunchSpec, BrowserSessionManager
    from sysu_jwxt_agent.schemas import ImportStateRequest

    auth = AuthService(
        tmp_path,
        browser_manager=BrowserSessionManager(
            BrowserLaunchSpec(
                headless=True,
                channel=None,
                storage_state_path=tmp_path / "storage_state.json",
            )
        ),
    )
    payload = ImportStateRequest(
        cookies=[
            {
                "name": "SESSION",
                "value": "abc",
                "domain": "jwxt.sysu.edu.cn",
                "path": "/",
                "secure": True,
                "httpOnly": True,
                "sameSite": "None",
            }
        ]
    )

    result = auth.import_state(payload)

    assert result.imported is True
    assert result.cookie_count == 1
    assert auth.state_file.exists()


def test_timetable_returns_live_payload_when_authenticated() -> None:
    client = TestClient(create_app())
    timetable = TimetableResponse(
        term="2025-2",
        stale=False,
        source="live",
        entries=[
            {
                "term": "2025-2",
                "course_name": "操作系统原理",
                "teacher": "陈鹏飞",
                "weekday": 1,
                "start_section": 1,
                "end_section": 2,
                "weeks": [5],
                "location": "东校园-公共教学楼D栋东D204",
                "raw_source": {"segments": []},
            }
        ],
    )

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch("sysu_jwxt_agent.services.jwxt.JwxtClient._fetch_live_timetable", return_value=timetable),
    ):
        response = client.get("/timetable")

    assert response.status_code == 200
    assert response.json()["term"] == "2025-2"
    assert response.json()["entries"][0]["course_name"] == "操作系统原理"
    assert "raw_source" not in response.json()["entries"][0]


def test_exams_returns_live_payload_when_authenticated() -> None:
    client = TestClient(create_app())
    exams = ExamsResponse(
        term="2025-2",
        stale=False,
        source="live",
        selected_exam_week={
            "exam_week_id": "1993161184323653634",
            "exam_week_name": "18-19周期末考",
            "start_date": "2026-06-29",
            "end_date": "2026-07-12",
        },
        exam_weeks=[
            {
                "exam_week_id": "1993161184323653634",
                "exam_week_name": "18-19周期末考",
                "start_date": "2026-06-29",
                "end_date": "2026-07-12",
            }
        ],
        entries=[],
        raw_records=[],
    )

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch("sysu_jwxt_agent.services.jwxt.JwxtClient._fetch_live_exams", return_value=exams),
    ):
        response = client.get("/exams")

    assert response.status_code == 200
    assert response.json()["term"] == "2025-2"
    assert response.json()["selected_exam_week"]["exam_week_name"] == "18-19周期末考"
    assert "raw_records" not in response.json()


def test_exams_returns_400_for_invalid_exam_week_id() -> None:
    client = TestClient(create_app())

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch(
            "sysu_jwxt_agent.services.jwxt.JwxtClient._fetch_live_exams",
            side_effect=__import__("sysu_jwxt_agent.services.jwxt", fromlist=["InvalidQueryError"]).InvalidQueryError(
                "Exam week invalid was not found for term 2024-1."
            ),
        ),
    ):
        response = client.get("/exams", params={"term": "2024-1", "exam_week_id": "invalid"})

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_query"


def test_timetable_can_include_raw_when_requested() -> None:
    client = TestClient(create_app())
    timetable = TimetableResponse(
        term="2025-2",
        stale=False,
        source="live",
        entries=[
            {
                "term": "2025-2",
                "course_name": "操作系统原理",
                "teacher": "陈鹏飞",
                "weekday": 1,
                "start_section": 1,
                "end_section": 2,
                "weeks": [5],
                "location": "东校园-公共教学楼D栋东D204",
                "raw_source": {"segments": [{"block": "操作系统原理"}]},
            }
        ],
    )

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch("sysu_jwxt_agent.services.jwxt.JwxtClient._fetch_live_timetable", return_value=timetable),
    ):
        response = client.get("/timetable", params={"include_raw": "true"})

    assert response.status_code == 200
    assert response.json()["entries"][0]["raw_source"]["segments"][0]["block"] == "操作系统原理"


def test_exams_can_include_raw_when_requested() -> None:
    client = TestClient(create_app())
    exams = ExamsResponse(
        term="2025-2",
        stale=False,
        source="live",
        selected_exam_week={
            "exam_week_id": "1993161184323653634",
            "exam_week_name": "18-19周期末考",
            "start_date": "2026-06-29",
            "end_date": "2026-07-12",
        },
        exam_weeks=[
            {
                "exam_week_id": "1993161184323653634",
                "exam_week_name": "18-19周期末考",
                "start_date": "2026-06-29",
                "end_date": "2026-07-12",
            }
        ],
        entries=[
            {
                "term": "2025-2",
                "exam_week_id": "1993161184323653634",
                "exam_week_name": "18-19周期末考",
                "course_name": "操作系统原理",
                "exam_date": "2026-06-30",
                "exam_time": "09:30-11:30",
                "duration_minutes": 120,
                "location": "东D204",
                "exam_stage": "结课考试",
                "exam_mode": "考试",
                "section_label": "1",
                "raw_source": {"cell": {"examSubjectName": "操作系统原理"}},
            }
        ],
        raw_records=[{"timetable": {}}],
    )

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch("sysu_jwxt_agent.services.jwxt.JwxtClient._fetch_live_exams", return_value=exams),
    ):
        response = client.get("/exams", params={"include_raw": "true"})

    assert response.status_code == 200
    assert response.json()["raw_records"] == [{"timetable": {}}]
    assert response.json()["entries"][0]["raw_source"]["cell"]["examSubjectName"] == "操作系统原理"
