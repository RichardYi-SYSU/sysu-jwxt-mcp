from fastapi import FastAPI

from sysu_jwxt_agent.api import build_router
from sysu_jwxt_agent.config import settings
from sysu_jwxt_agent.services.auth import AuthService
from sysu_jwxt_agent.services.browser import BrowserLaunchSpec, BrowserSessionManager
from sysu_jwxt_agent.services.cache import TimetableCache
from sysu_jwxt_agent.services.jwxt import JwxtClient


def create_app() -> FastAPI:
    browser_manager = BrowserSessionManager(
        BrowserLaunchSpec(
            headless=settings.browser_headless,
            channel=settings.browser_channel,
            storage_state_path=settings.state_dir / "storage_state.json",
        )
    )
    auth_service = AuthService(settings.state_dir, browser_manager=browser_manager)
    cache = TimetableCache(settings.cache_dir)
    jwxt_client = JwxtClient(
        auth_service=auth_service,
        cache=cache,
        browser_manager=browser_manager,
    )

    app = FastAPI(
        title="SYSU JWXT Agent",
        version="0.1.0",
        description="Local API for authorized timetable access from SYSU JWXT.",
    )
    app.include_router(build_router(jwxt_client=jwxt_client, auth_service=auth_service))
    return app


app = create_app()
