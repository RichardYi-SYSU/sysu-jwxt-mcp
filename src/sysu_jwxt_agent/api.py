from fastapi import APIRouter, Depends, HTTPException, Query, status

from sysu_jwxt_agent.schemas import (
    ExamsResponse,
    GradesResponse,
    HealthResponse,
    ImportStateRequest,
    ImportStateResponse,
    KeepaliveStatus,
    SessionStatus,
    TimetableResponse,
)
from sysu_jwxt_agent.services.jwxt import (
    AuthenticationRequiredError,
    InvalidQueryError,
    JwxtClient,
    UpstreamNotImplementedError,
)


def build_router(jwxt_client: JwxtClient, auth_service, keepalive_service=None) -> APIRouter:
    router = APIRouter()

    def get_client() -> JwxtClient:
        return jwxt_client

    @router.get("/health", response_model=HealthResponse)
    async def health() -> HealthResponse:
        return HealthResponse(status="ok")

    @router.post("/auth/login", response_model=SessionStatus)
    async def login() -> SessionStatus:
        return auth_service.login()

    @router.post("/auth/refresh", response_model=SessionStatus)
    async def refresh() -> SessionStatus:
        return auth_service.refresh()

    @router.post("/auth/import-state", response_model=ImportStateResponse)
    async def import_state(payload: ImportStateRequest) -> ImportStateResponse:
        return auth_service.import_state(payload)

    @router.get("/auth/keepalive/status", response_model=KeepaliveStatus, response_model_exclude_none=True)
    async def keepalive_status() -> KeepaliveStatus:
        if keepalive_service is None:
            return KeepaliveStatus(enabled=False, interval_seconds=0, running=False)
        return keepalive_service.status()

    @router.post("/auth/keepalive/start", response_model=KeepaliveStatus, response_model_exclude_none=True)
    async def keepalive_start() -> KeepaliveStatus:
        if keepalive_service is None:
            return KeepaliveStatus(enabled=False, interval_seconds=0, running=False)
        return keepalive_service.start()

    @router.post("/auth/keepalive/stop", response_model=KeepaliveStatus, response_model_exclude_none=True)
    async def keepalive_stop() -> KeepaliveStatus:
        if keepalive_service is None:
            return KeepaliveStatus(enabled=False, interval_seconds=0, running=False)
        return keepalive_service.stop()

    @router.post("/auth/keepalive/ping", response_model=KeepaliveStatus, response_model_exclude_none=True)
    async def keepalive_ping() -> KeepaliveStatus:
        if keepalive_service is None:
            return KeepaliveStatus(enabled=False, interval_seconds=0, running=False)
        return keepalive_service.ping_once()

    @router.get("/timetable", response_model=TimetableResponse, response_model_exclude_none=True)
    def get_timetable(
        term: str = Query(default="current"),
        include_raw: bool = Query(default=False),
        client: JwxtClient = Depends(get_client),
    ) -> TimetableResponse:
        try:
            return client.get_timetable(term=term, include_raw=include_raw)
        except AuthenticationRequiredError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "unauthenticated",
                    "message": str(exc),
                },
            ) from exc
        except UpstreamNotImplementedError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail={
                    "code": "upstream_not_implemented",
                    "message": str(exc),
                },
            ) from exc

    @router.get("/exams", response_model=ExamsResponse, response_model_exclude_none=True)
    def get_exams(
        term: str = Query(default="current"),
        exam_week_id: str | None = Query(default=None),
        include_raw: bool = Query(default=False),
        client: JwxtClient = Depends(get_client),
    ) -> ExamsResponse:
        try:
            return client.get_exams(term=term, exam_week_id=exam_week_id, include_raw=include_raw)
        except AuthenticationRequiredError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "unauthenticated",
                    "message": str(exc),
                },
            ) from exc
        except InvalidQueryError as exc:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail={
                    "code": "invalid_query",
                    "message": str(exc),
                },
            ) from exc
        except UpstreamNotImplementedError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail={
                    "code": "upstream_not_implemented",
                    "message": str(exc),
                },
            ) from exc

    @router.get("/grades", response_model=GradesResponse, response_model_exclude_none=True)
    def get_grades(
        term: str = Query(default="current"),
        include_raw: bool = Query(default=False),
        client: JwxtClient = Depends(get_client),
    ) -> GradesResponse:
        try:
            return client.get_grades(term=term, include_raw=include_raw)
        except AuthenticationRequiredError as exc:
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail={
                    "code": "unauthenticated",
                    "message": str(exc),
                },
            ) from exc
        except UpstreamNotImplementedError as exc:
            raise HTTPException(
                status_code=status.HTTP_501_NOT_IMPLEMENTED,
                detail={
                    "code": "upstream_not_implemented",
                    "message": str(exc),
                },
            ) from exc

    return router
