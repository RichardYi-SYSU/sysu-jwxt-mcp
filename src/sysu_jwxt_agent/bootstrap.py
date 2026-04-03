from dataclasses import dataclass

from sysu_jwxt_agent.config import settings
from sysu_jwxt_agent.services.auth import AuthService
from sysu_jwxt_agent.services.browser import BrowserLaunchSpec, BrowserSessionManager
from sysu_jwxt_agent.services.cache import TimetableCache
from sysu_jwxt_agent.services.jwxt import JwxtClient
from sysu_jwxt_agent.services.keepalive import SessionKeepaliveService


@dataclass
class AppServices:
    browser_manager: BrowserSessionManager
    auth_service: AuthService
    keepalive_service: SessionKeepaliveService
    cache: TimetableCache
    jwxt_client: JwxtClient


def create_services() -> AppServices:
    browser_manager = BrowserSessionManager(
        BrowserLaunchSpec(
            headless=settings.browser_headless,
            channel=settings.browser_channel,
            storage_state_path=settings.state_dir / "storage_state.json",
        )
    )
    auth_service = AuthService(settings.state_dir, browser_manager=browser_manager)
    keepalive_service = SessionKeepaliveService(
        auth_service=auth_service,
        interval_seconds=settings.keepalive_interval_seconds,
        jitter_seconds=settings.keepalive_jitter_seconds,
    )
    cache = TimetableCache(settings.cache_dir)
    jwxt_client = JwxtClient(
        auth_service=auth_service,
        cache=cache,
        browser_manager=browser_manager,
    )
    return AppServices(
        browser_manager=browser_manager,
        auth_service=auth_service,
        keepalive_service=keepalive_service,
        cache=cache,
        jwxt_client=jwxt_client,
    )
