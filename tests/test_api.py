from fastapi.testclient import TestClient
from unittest.mock import patch

from sysu_jwxt_agent.main import create_app
from sysu_jwxt_agent.schemas import (
    CetScoresResponse,
    EmptyClassroomsResponse,
    ExamsResponse,
    GradesResponse,
    QrLoginConfirmResponse,
    QrLoginStartResponse,
    QrLoginStatusResponse,
    TimetableResponse,
)


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


def test_qr_login_start_route() -> None:
    client = TestClient(create_app())

    with patch("sysu_jwxt_agent.services.auth.AuthService.start_qr_login") as mocked_start:
        mocked_start.return_value = QrLoginStartResponse(
            login_session_id="abc12345",
            status="pending",
            qr_image_base64="ZmFrZQ==",
            qr_page_url="https://cas.sysu.edu.cn/esc-sso/login",
            qr_png_path="data/state/qr-login/abc12345.png",
            expires_at="2026-04-03T00:00:00+00:00",
            message="ok",
        )
        response = client.post("/auth/qr/start")

    assert response.status_code == 200
    assert response.json()["login_session_id"] == "abc12345"
    assert response.json()["status"] == "pending"
    assert response.json()["qr_png_path"] == "data/state/qr-login/abc12345.png"


def test_qr_login_start_returns_503_on_bootstrap_error() -> None:
    client = TestClient(create_app())
    from sysu_jwxt_agent.services.auth import QrLoginStartError

    with patch(
        "sysu_jwxt_agent.services.auth.AuthService.start_qr_login",
        side_effect=QrLoginStartError("playwright failed"),
    ):
        response = client.post("/auth/qr/start")

    assert response.status_code == 503
    assert response.json()["detail"]["code"] == "qr_start_failed"


def test_qr_login_status_route() -> None:
    client = TestClient(create_app())

    with patch("sysu_jwxt_agent.services.auth.AuthService.get_qr_login_status") as mocked_status:
        mocked_status.return_value = QrLoginStatusResponse(
            login_session_id="abc12345",
            status="success",
            authenticated=True,
            expires_at="2026-04-03T00:00:00+00:00",
            state_persisted=True,
            state_path="data/state/storage_state.json",
            cookie_count=3,
            qr_png_path="data/state/qr-login/abc12345.png",
            trace_path="data/state/qr-login/abc12345.trace.json",
            message="persisted",
        )
        response = client.get("/auth/qr/status", params={"login_session_id": "abc12345"})

    assert response.status_code == 200
    assert response.json()["authenticated"] is True
    assert response.json()["state_persisted"] is True
    assert response.json()["cookie_count"] == 3


def test_qr_login_status_404_for_unknown_session() -> None:
    client = TestClient(create_app())
    from sysu_jwxt_agent.services.auth import QrLoginSessionNotFoundError

    with patch(
        "sysu_jwxt_agent.services.auth.AuthService.get_qr_login_status",
        side_effect=QrLoginSessionNotFoundError("not found"),
    ):
        response = client.get("/auth/qr/status", params={"login_session_id": "missing123"})

    assert response.status_code == 404
    assert response.json()["detail"]["code"] == "qr_session_not_found"


def test_qr_login_confirm_route() -> None:
    client = TestClient(create_app())

    with patch("sysu_jwxt_agent.services.auth.AuthService.confirm_qr_login") as mocked_confirm:
        mocked_confirm.return_value = QrLoginConfirmResponse(
            login_session_id="abc12345",
            status="success",
            authenticated=True,
            imported=True,
            cookie_count=3,
            state_path="data/state/storage_state.json",
            message="persisted",
        )
        response = client.post("/auth/qr/confirm", params={"login_session_id": "abc12345"})

    assert response.status_code == 200
    assert response.json()["status"] == "success"
    assert response.json()["imported"] is True


def test_qr_login_confirm_route_is_compatible_after_auto_persist() -> None:
    client = TestClient(create_app())

    with patch("sysu_jwxt_agent.services.auth.AuthService.confirm_qr_login") as mocked_confirm:
        mocked_confirm.return_value = QrLoginConfirmResponse(
            login_session_id="abc12345",
            status="success",
            authenticated=True,
            imported=True,
            cookie_count=3,
            state_path="data/state/storage_state.json",
            message="already persisted",
        )
        response = client.post("/auth/qr/confirm", params={"login_session_id": "abc12345"})

    assert response.status_code == 200
    assert response.json()["message"] == "already persisted"


def test_qr_login_confirm_409_when_not_ready() -> None:
    client = TestClient(create_app())
    from sysu_jwxt_agent.services.auth import QrLoginNotReadyError

    with patch(
        "sysu_jwxt_agent.services.auth.AuthService.confirm_qr_login",
        side_effect=QrLoginNotReadyError("not ready"),
    ):
        response = client.post("/auth/qr/confirm", params={"login_session_id": "abc12345"})

    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "qr_login_not_ready"


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


def test_exams_accepts_exam_week_type_query() -> None:
    client = TestClient(create_app())

    with patch("sysu_jwxt_agent.services.jwxt.JwxtClient.get_exams") as mocked_get_exams:
        mocked_get_exams.return_value = ExamsResponse(
            term="2025-2",
            stale=False,
            source="live",
            selected_exam_week=None,
            exam_weeks=[],
            entries=[],
            raw_records=None,
        )

        response = client.get(
            "/exams",
            params={"term": "2025-2", "exam_week_type": "18-19周期末考"},
        )

    assert response.status_code == 200
    mocked_get_exams.assert_called_once_with(
        term="2025-2",
        exam_week_id=None,
        exam_week_type="18-19周期末考",
        include_raw=False,
    )


def test_exams_rejects_unknown_exam_week_type_query() -> None:
    client = TestClient(create_app())

    response = client.get(
        "/exams",
        params={"term": "2025-2", "exam_week_type": "其他类型"},
    )

    assert response.status_code == 422


def test_empty_classrooms_requires_date_campus_and_section_range() -> None:
    client = TestClient(create_app())

    response = client.get("/classrooms/empty")

    assert response.status_code == 422


def test_empty_classrooms_accepts_required_query() -> None:
    client = TestClient(create_app())

    with patch("sysu_jwxt_agent.services.jwxt.JwxtClient.get_empty_classrooms") as mocked_get_empty_classrooms:
        mocked_get_empty_classrooms.return_value = EmptyClassroomsResponse(
            date="2026-04-02",
            campus="东校园",
            campus_id="5063559",
            section_range="1-4",
            stale=False,
            source="live",
            entries=[],
            raw_records=None,
        )

        response = client.get(
            "/classrooms/empty",
            params={"date": "2026-04-02", "campus": "东校园", "section_range": "1-4"},
        )

    assert response.status_code == 200
    mocked_get_empty_classrooms.assert_called_once_with(
        date_value="2026-04-02",
        campus="东校园",
        section_range="1-4",
        include_raw=False,
    )


def test_empty_classrooms_returns_400_for_invalid_section_range() -> None:
    client = TestClient(create_app())

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch(
            "sysu_jwxt_agent.services.jwxt.JwxtClient.get_empty_classrooms",
            side_effect=__import__("sysu_jwxt_agent.services.jwxt", fromlist=["InvalidQueryError"]).InvalidQueryError(
                "section_range must use X-Y within 1-16, received 8-2."
            ),
        ),
    ):
        response = client.get(
            "/classrooms/empty",
            params={"date": "2026-04-02", "campus": "东校园", "section_range": "8-2"},
        )

    assert response.status_code == 400
    assert response.json()["detail"]["code"] == "invalid_query"


def test_cet_scores_accepts_level_query() -> None:
    client = TestClient(create_app())

    with patch("sysu_jwxt_agent.services.jwxt.JwxtClient.get_cet_scores") as mocked_get_cet_scores:
        mocked_get_cet_scores.return_value = CetScoresResponse(
            level=4,
            stale=False,
            source="live",
            total_records=2,
            matched_records=1,
            entries=[{"level": "CET-4", "score": "612"}],
        )

        response = client.get("/cet-scores", params={"level": 4})

    assert response.status_code == 200
    mocked_get_cet_scores.assert_called_once_with(level=4, include_raw=False)


def test_cet_scores_rejects_invalid_level() -> None:
    client = TestClient(create_app())

    response = client.get("/cet-scores", params={"level": 5})

    assert response.status_code == 422


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


def test_timetable_supports_week_query() -> None:
    client = TestClient(create_app())
    timetable = TimetableResponse(
        term="2025-2",
        week=10,
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
                "weeks": [10],
                "location": "东D204",
            }
        ],
    )

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch("sysu_jwxt_agent.services.jwxt.JwxtClient._fetch_live_timetable", return_value=timetable),
    ):
        response = client.get("/timetable", params={"term": "2025-2", "week": 10})

    assert response.status_code == 200
    assert response.json()["term"] == "2025-2"
    assert response.json()["week"] == 10
    assert response.json()["entries"][0]["weeks"] == [10]


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


def test_grades_returns_live_payload_when_authenticated() -> None:
    client = TestClient(create_app())
    grades = GradesResponse(
        term="2025-2",
        stale=False,
        source="live",
        entries=[
            {
                "term": "2025-2",
                "course_name": "操作系统原理",
                "course_code": "CS2001",
                "course_type": "专必",
                "credit": 3.0,
                "score": "92",
                "grade_point": 4.0,
                "rank": "1/30",
                "raw_source": {"score": "92"},
            }
        ],
        summary={"passed": 1},
        distribution=[{"name": "90-100", "value": 1}],
        raw_records=[{"courseName": "操作系统原理"}],
    )

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch("sysu_jwxt_agent.services.jwxt.JwxtClient._fetch_live_grades", return_value=grades),
    ):
        response = client.get("/grades")

    assert response.status_code == 200
    assert response.json()["term"] == "2025-2"
    assert response.json()["entries"][0]["course_name"] == "操作系统原理"
    assert response.json()["entries"][0]["course_type"] == "专必"
    assert response.json()["entries"][0]["rank"] == "1/30"
    assert "raw_source" not in response.json()["entries"][0]
    assert "raw_records" not in response.json()


def test_grades_can_include_raw_when_requested() -> None:
    client = TestClient(create_app())
    grades = GradesResponse(
        term="2025-2",
        stale=False,
        source="live",
        entries=[
            {
                "term": "2025-2",
                "course_name": "操作系统原理",
                "course_type": "专必",
                "score": "92",
                "rank": "1/30",
                "raw_source": {"score": "92"},
            }
        ],
        summary={},
        distribution=[],
        raw_records=[{"courseName": "操作系统原理"}],
    )

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch("sysu_jwxt_agent.services.jwxt.JwxtClient._fetch_live_grades", return_value=grades),
    ):
        response = client.get("/grades", params={"include_raw": "true"})

    assert response.status_code == 200
    assert response.json()["entries"][0]["raw_source"]["score"] == "92"
    assert response.json()["entries"][0]["course_type"] == "专必"
    assert response.json()["entries"][0]["rank"] == "1/30"
    assert response.json()["raw_records"] == [{"courseName": "操作系统原理"}]


def test_keepalive_routes_work() -> None:
    client = TestClient(create_app())

    with (
        patch("sysu_jwxt_agent.services.auth.AuthService.is_authenticated", return_value=True),
        patch("sysu_jwxt_agent.services.auth.AuthService.keepalive_probe", return_value=True),
    ):
        status = client.get("/auth/keepalive/status")
        assert status.status_code == 200
        assert status.json()["enabled"] is True
        assert status.json()["interval_seconds"] == 300
        assert status.json()["jitter_seconds"] == 20

        started = client.post("/auth/keepalive/start")
        assert started.status_code == 200
        assert started.json()["running"] is True

        ping = client.post("/auth/keepalive/ping")
        assert ping.status_code == 200
        assert ping.json()["last_ok"] is True
        assert ping.json()["tick_count"] >= 1
        assert ping.json()["consecutive_failures"] == 0

        stopped = client.post("/auth/keepalive/stop")
        assert stopped.status_code == 200
        assert stopped.json()["running"] is False
