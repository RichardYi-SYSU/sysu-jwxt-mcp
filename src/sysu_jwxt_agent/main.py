from fastapi import FastAPI

from sysu_jwxt_agent.api import build_router
from sysu_jwxt_agent.bootstrap import create_services
from sysu_jwxt_agent.config import settings


def create_app() -> FastAPI:
    services = create_services()

    app = FastAPI(
        title="SYSU JWXT Agent",
        version="0.1.0",
        description="Local API for authorized timetable access from SYSU JWXT.",
    )
    app.include_router(
        build_router(
            jwxt_client=services.jwxt_client,
            auth_service=services.auth_service,
            keepalive_service=services.keepalive_service,
        )
    )
    return app


app = create_app()
