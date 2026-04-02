import json
import time
from pathlib import Path

import httpx

from sysu_jwxt_agent.config import settings
from sysu_jwxt_agent.schemas import CookieItem, ImportStateRequest, ImportStateResponse, SessionStatus
from sysu_jwxt_agent.services.browser import BrowserSessionManager


class AuthService:
    def __init__(self, state_dir: Path, browser_manager: BrowserSessionManager) -> None:
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._state_dir / "storage_state.json"
        self._browser_manager = browser_manager

    @property
    def has_session(self) -> bool:
        return self._state_file.exists()

    @property
    def state_file(self) -> Path:
        return self._state_file

    def is_authenticated(self) -> bool:
        live_status = self._probe_upstream_status()
        return bool(live_status.get("data"))

    def login(self) -> SessionStatus:
        live_status = self._probe_upstream_status()
        cas_login_url = self._fetch_cas_login_url()
        authenticated = bool(live_status.get("data"))

        if authenticated:
            return SessionStatus(
                authenticated=True,
                message="Upstream login status indicates an authenticated session.",
                cas_login_url=cas_login_url,
                upstream_code=live_status.get("code"),
            )

        if self.has_session:
            message = (
                "A local storage state file exists, but the upstream login status still reports "
                "an unauthenticated state. Re-login or import a valid session."
            )
        else:
            message = (
                "No reusable session was found. The upstream login status API reports an unauthenticated state. "
                "Use the CAS login URL or import a valid storage state. "
                f"Expected strategy: {self._browser_manager.describe_login_strategy()}"
            )

        return SessionStatus(
            authenticated=False,
            login_required=True,
            manual_step_required=True,
            message=message,
            cas_login_url=cas_login_url,
            upstream_code=live_status.get("code"),
        )

    def refresh(self) -> SessionStatus:
        live_status = self._probe_upstream_status()
        authenticated = bool(live_status.get("data"))

        if authenticated:
            return SessionStatus(
                authenticated=True,
                message="Upstream login status indicates an authenticated session.",
                cas_login_url=self._fetch_cas_login_url(),
                upstream_code=live_status.get("code"),
            )

        return SessionStatus(
            authenticated=False,
            login_required=True,
            manual_step_required=True,
            message=(
                "Upstream still reports an unauthenticated state. "
                "Run the login flow first or import a valid browser session."
            ),
            cas_login_url=self._fetch_cas_login_url(),
            upstream_code=live_status.get("code"),
        )

    def import_state(self, payload: ImportStateRequest) -> ImportStateResponse:
        if payload.storage_state is not None:
            state = payload.storage_state
        else:
            cookies = [cookie.model_dump(exclude_none=True) for cookie in (payload.cookies or [])]
            state = {
                "cookies": cookies,
                "origins": payload.origins or [],
            }

        normalized = self._normalize_storage_state(state)
        self._state_file.write_text(
            json.dumps(normalized, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        return ImportStateResponse(
            imported=True,
            cookie_count=len(normalized["cookies"]),
            state_path=str(self._state_file),
            message=(
                "Session state imported. Run /auth/refresh next to verify whether the "
                "imported cookies establish an authenticated JWXT session."
            ),
        )

    def _probe_upstream_status(self) -> dict:
        url = f"{settings.base_url}/api/login/status"
        with self._build_client() as client:
            response = client.get(url, params={"_t": 1775129145})
            response.raise_for_status()
            return response.json()

    def keepalive_probe(self) -> bool:
        with self._build_client() as client:
            status_resp = client.get(f"{settings.base_url}/api/login/status", params={"_t": int(time.time())})
            status_resp.raise_for_status()
            status_json = status_resp.json()
            if not bool(status_json.get("data")):
                return False

            acad_resp = client.get(f"{settings.base_url}/base-info/acadyearterm/showNewAcadlist")
            acad_resp.raise_for_status()
            cas_resp = client.get(f"{settings.base_url}/api/sso/cas/login")
            if cas_resp.status_code not in {200, 301, 302, 303, 307, 308}:
                return False
            return True

    def _fetch_cas_login_url(self) -> str | None:
        url = f"{settings.base_url}/api/sso/cas/login"
        with self._build_client() as client:
            response = client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                return response.headers.get("location")
        return None

    def _normalize_storage_state(self, state: dict) -> dict:
        cookies = state.get("cookies", [])
        origins = state.get("origins", [])
        normalized_cookies = []

        for cookie in cookies:
            item = CookieItem.model_validate(cookie)
            normalized_cookies.append(item.model_dump(exclude_none=True))

        return {
            "cookies": normalized_cookies,
            "origins": origins,
        }

    def _build_client(self) -> httpx.Client:
        cookies = self._load_cookie_jar()
        return httpx.Client(
            timeout=settings.timeout_seconds,
            follow_redirects=False,
            cookies=cookies,
        )

    def _load_cookie_jar(self) -> httpx.Cookies:
        jar = httpx.Cookies()
        if not self._state_file.exists():
            return jar

        payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        for cookie in payload.get("cookies", []):
            name = cookie.get("name")
            value = cookie.get("value")
            domain = cookie.get("domain")
            path = cookie.get("path", "/")
            if not name or value is None:
                continue
            jar.set(name, value, domain=domain, path=path)
        return jar
