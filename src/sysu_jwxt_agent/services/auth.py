import json
import time
from concurrent.futures import ThreadPoolExecutor
from base64 import b64encode
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from threading import Lock
from uuid import uuid4

import httpx
from playwright.sync_api import APIResponse, Frame, Page, Response, sync_playwright

from sysu_jwxt_agent.config import settings
from sysu_jwxt_agent.schemas import (
    CookieItem,
    ImportStateRequest,
    ImportStateResponse,
    QrLoginConfirmResponse,
    QrLoginStartResponse,
    QrLoginStatusResponse,
    SessionStatus,
)
from sysu_jwxt_agent.services.browser import BrowserSessionManager


class QrLoginSessionNotFoundError(Exception):
    pass


class QrLoginNotReadyError(Exception):
    pass


class QrLoginStartError(Exception):
    pass


@dataclass
class _QrLoginRuntimeSession:
    session_id: str
    playwright: object
    browser: object
    context: object
    page: object
    expires_at: datetime
    status: str = "pending"
    last_error: str | None = None
    cas_login_url: str | None = None
    wecom_iframe_url: str | None = None
    qr_page_url: str | None = None
    qr_png_path: Path | None = None
    trace_path: Path | None = None
    redirect_trace: list[dict] = field(default_factory=list)
    state_persisted: bool = False
    state_path: Path | None = None
    cookie_count: int = 0
    latest_ticket_url: str | None = None


class AuthService:
    def __init__(self, state_dir: Path, browser_manager: BrowserSessionManager) -> None:
        self._state_dir = state_dir
        self._state_dir.mkdir(parents=True, exist_ok=True)
        self._state_file = self._state_dir / "storage_state.json"
        self._browser_manager = browser_manager
        self._qr_lock = Lock()
        self._qr_sessions: dict[str, _QrLoginRuntimeSession] = {}
        # Playwright sync objects are thread-affine. Keep all QR session operations
        # on a dedicated single thread to avoid greenlet/thread switch errors.
        self._qr_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix="jwxt-qr")

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

    def start_qr_login(self) -> QrLoginStartResponse:
        return self._qr_executor.submit(self._start_qr_login_inner).result()

    def _start_qr_login_inner(self) -> QrLoginStartResponse:
        self._cleanup_qr_sessions()
        self._close_all_qr_sessions()
        session_id = uuid4().hex
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.qr_login_session_ttl_seconds)
        cas_login_url = self._fetch_cas_login_url(pattern="student-login") or (
            "https://cas.sysu.edu.cn/esc-sso/login"
            f"?service={self._student_service_url().replace(':', '%3A').replace('/', '%2F').replace('?', '%3F').replace('=', '%3D')}"
        )
        qr_dir = self._state_dir / "qr-login"
        qr_dir.mkdir(parents=True, exist_ok=True)
        qr_png_path = qr_dir / f"{session_id}.png"
        trace_path = qr_dir / f"{session_id}.trace.json"
        playwright = None
        browser = None
        context = None
        page = None
        redirect_trace: list[dict] = []
        iframe_url: str | None = None
        try:
            playwright = sync_playwright().start()
            browser = playwright.chromium.launch(
                headless=self._browser_manager.headless,
                channel=self._browser_manager.channel,
            )
            context = browser.new_context()
            page = context.new_page()
            self._attach_qr_trace_listeners(page=page, redirect_trace=redirect_trace)
            page.goto(cas_login_url, wait_until="domcontentloaded", timeout=30000)
            qr_frame = self._wait_for_qr_iframe(page)
            screenshot_bytes = self._capture_qr_png(page=page, frame=qr_frame)
            qr_png_path.write_bytes(screenshot_bytes)
            qr_image_base64 = b64encode(screenshot_bytes).decode("ascii")
            qr_ascii = self._extract_qr_ascii(page)
            page_url = str(page.url)
            iframe_url = str(qr_frame.url) if qr_frame is not None else None
        except Exception as exc:
            if context is not None:
                try:
                    context.close()
                except Exception:
                    pass
            if browser is not None:
                try:
                    browser.close()
                except Exception:
                    pass
            if playwright is not None:
                try:
                    playwright.stop()
                except Exception:
                    pass
            raise QrLoginStartError(
                "Failed to start QR login browser session. "
                "Check Playwright browser installation and headless settings. "
                f"cause={exc}"
            ) from exc

        runtime = _QrLoginRuntimeSession(
            session_id=session_id,
            playwright=playwright,
            browser=browser,
            context=context,
            page=page,
            expires_at=expires_at,
            cas_login_url=cas_login_url,
            wecom_iframe_url=iframe_url,
            qr_page_url=page_url,
            qr_png_path=qr_png_path,
            trace_path=trace_path,
            redirect_trace=redirect_trace,
            state_path=self._state_file,
        )
        self._write_trace(runtime)
        with self._qr_lock:
            self._qr_sessions[session_id] = runtime

        return QrLoginStartResponse(
            login_session_id=session_id,
            status="pending",
            qr_image_base64=qr_image_base64,
            qr_ascii=qr_ascii,
            qr_page_url=page_url,
            qr_png_path=str(qr_png_path),
            expires_at=expires_at.isoformat(),
            message="QR session created. Display qr_ascii or qr_png_path to the user and poll /auth/qr/status.",
        )

    def get_qr_login_status(self, login_session_id: str) -> QrLoginStatusResponse:
        return self._qr_executor.submit(self._get_qr_login_status_inner, login_session_id).result()

    def _get_qr_login_status_inner(self, login_session_id: str) -> QrLoginStatusResponse:
        runtime = self._get_qr_runtime(login_session_id)
        if self._is_expired(runtime):
            self._close_qr_session(runtime, reason="expired")
            return QrLoginStatusResponse(
                login_session_id=login_session_id,
                status="expired",
                authenticated=False,
                expires_at=runtime.expires_at.isoformat(),
                qr_png_path=str(runtime.qr_png_path) if runtime.qr_png_path is not None else None,
                trace_path=str(runtime.trace_path) if runtime.trace_path is not None else None,
                message="QR login session expired. Start a new session.",
            )

        authenticated = self._probe_qr_authenticated(runtime)
        if authenticated:
            runtime.status = "success"
            self._persist_qr_runtime(runtime)
            message = "Login confirmed and storage_state persisted."
        elif runtime.status == "confirmed":
            message = "CAS confirmed; finalizing JWXT SSO, please poll again."
        else:
            message = "Waiting for scan/confirmation."
        self._write_trace(runtime)

        return QrLoginStatusResponse(
            login_session_id=login_session_id,
            status=runtime.status,
            authenticated=authenticated,
            expires_at=runtime.expires_at.isoformat(),
            last_error=runtime.last_error,
            state_persisted=runtime.state_persisted,
            state_path=str(runtime.state_path) if runtime.state_persisted and runtime.state_path is not None else None,
            cookie_count=runtime.cookie_count if runtime.state_persisted else 0,
            qr_png_path=str(runtime.qr_png_path) if runtime.qr_png_path is not None else None,
            trace_path=str(runtime.trace_path) if runtime.trace_path is not None else None,
            message=message,
        )

    def confirm_qr_login(self, login_session_id: str) -> QrLoginConfirmResponse:
        return self._qr_executor.submit(self._confirm_qr_login_inner, login_session_id).result()

    def _confirm_qr_login_inner(self, login_session_id: str) -> QrLoginConfirmResponse:
        runtime = self._get_qr_runtime(login_session_id)
        if self._is_expired(runtime):
            self._close_qr_session(runtime, reason="expired")
            raise QrLoginNotReadyError("QR login session expired. Start a new session.")

        authenticated = self._probe_qr_authenticated(runtime)
        if authenticated and not runtime.state_persisted:
            self._persist_qr_runtime(runtime)
        if not authenticated:
            raise QrLoginNotReadyError("QR login not completed yet. Continue polling /auth/qr/status.")

        cookie_count = runtime.cookie_count
        self._close_qr_session(runtime)

        return QrLoginConfirmResponse(
            login_session_id=login_session_id,
            status="success",
            authenticated=True,
            imported=runtime.state_persisted,
            cookie_count=cookie_count,
            state_path=str(self._state_file),
            message="QR login confirmed. storage_state is already persisted.",
        )

    def _probe_upstream_status(self) -> dict:
        url = f"{settings.base_url}/api/login/status"
        with self._build_client() as client:
            response = client.get(url, params={"_t": int(time.time())})
            response.raise_for_status()
            return response.json()

    def _probe_upstream_status_with_cookies(self, cookies: list[dict]) -> dict:
        jar = httpx.Cookies()
        for cookie in cookies:
            name = cookie.get("name")
            value = cookie.get("value")
            domain = cookie.get("domain")
            path = cookie.get("path", "/")
            if not name or value is None:
                continue
            jar.set(name, value, domain=domain, path=path)
        with httpx.Client(
            timeout=settings.timeout_seconds,
            follow_redirects=False,
            cookies=jar,
        ) as client:
            response = client.get(
                f"{settings.base_url}/api/login/status",
                params={"_t": int(time.time())},
            )
            response.raise_for_status()
            return response.json()

    def keepalive_probe(self) -> bool:
        with self._build_client() as client:
            status_resp = client.get(f"{settings.base_url}/api/login/status", params={"_t": int(time.time())})
            status_resp.raise_for_status()
            status_json = status_resp.json()
            if not bool(status_json.get("data")):
                return False

            # Keepalive is primarily determined by authenticated login status.
            # Additional touch request is best-effort to keep active JWXT context.
            try:
                acad_resp = client.get(
                    f"{settings.base_url}/base-info/acadyearterm/showNewAcadlist",
                    params={"_t": int(time.time() * 1000)},
                    headers=self._jwxt_ajax_headers(),
                )
                if acad_resp.status_code not in {200, 304}:
                    return True
                payload = acad_resp.json()
                if payload.get("code") != 200:
                    return True
            except Exception:
                # Non-fatal for keepalive validity; login/status above is authoritative.
                return True
            return True

    def _jwxt_ajax_headers(self) -> dict[str, str]:
        return {
            "X-Requested-With": "XMLHttpRequest",
            "Accept": "application/json, text/plain, */*",
            "Referer": f"{settings.base_url}/#/student",
            "Origin": "https://jwxt.sysu.edu.cn",
            "moduleid": "null",
            "menuid": "null",
            "lastaccesstime": str(int(time.time() * 1000)),
        }

    def _fetch_cas_login_url(self, pattern: str | None = None) -> str | None:
        query = f"?pattern={pattern}" if pattern else ""
        url = f"{settings.base_url}/api/sso/cas/login{query}"
        with self._build_client() as client:
            response = client.get(url)
            if response.status_code in {301, 302, 303, 307, 308}:
                return response.headers.get("location")
        return None

    def _student_service_url(self) -> str:
        return f"{settings.base_url}/api/sso/cas/login?pattern=student-login"

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

    def _try_switch_to_wecom_qr(self, page: Page) -> None:
        selectors = [
            "text=企业微信扫码登录",
            "text=企业微信扫码",
            "text=扫码登录",
            "text=企业微信",
            "a:has-text('企业微信')",
            "button:has-text('企业微信')",
        ]
        for selector in selectors:
            try:
                locator = page.locator(selector).first
                if locator.is_visible(timeout=1200):
                    locator.click(timeout=1200)
                    page.wait_for_timeout(400)
                    return
            except Exception:
                continue

    def _wait_for_qr_iframe(self, page: Page) -> Frame | None:
        try:
            page.wait_for_selector(".qrcode-container iframe", timeout=8000)
            page.wait_for_timeout(1200)
        except Exception:
            return None
        for frame in page.frames:
            if frame == page.main_frame:
                continue
            url = str(frame.url)
            if "weixin" in url or "wecom" in url or "work.weixin" in url or "wxwork" in url:
                return frame
        frames = [frame for frame in page.frames if frame != page.main_frame]
        return frames[0] if frames else None

    def _capture_qr_png(self, page: Page, frame: Frame | None) -> bytes:
        if frame is not None:
            image_selectors = [
                "img[src*='qr']",
                "img[src*='QR']",
                "img[src*='qrcode']",
                "img",
                "canvas",
            ]
            for selector in image_selectors:
                try:
                    locator = frame.locator(selector).first
                    if locator.is_visible(timeout=1500):
                        return locator.screenshot(type="png")
                except Exception:
                    continue
        return page.screenshot(type="png", full_page=True)

    def _extract_qr_ascii(self, page: Page) -> str | None:
        for frame in page.frames:
            result = self._extract_qr_ascii_from_frame(frame)
            if result:
                return result
        return None

    def _extract_qr_ascii_from_frame(self, frame: Frame) -> str | None:
        try:
            return frame.evaluate(
                """() => {
                  function toGrayMatrix(canvas) {
                    const ctx = canvas.getContext('2d');
                    if (!ctx) return null;
                    const w = canvas.width;
                    const h = canvas.height;
                    if (!w || !h) return null;
                    const rgba = ctx.getImageData(0, 0, w, h).data;
                    const gray = new Uint8Array(w * h);
                    let minX = w, minY = h, maxX = -1, maxY = -1;
                    for (let y = 0; y < h; y++) {
                      for (let x = 0; x < w; x++) {
                        const i = (y * w + x) * 4;
                        const g = Math.round(0.299 * rgba[i] + 0.587 * rgba[i + 1] + 0.114 * rgba[i + 2]);
                        gray[y * w + x] = g;
                        if (g < 100) {
                          if (x < minX) minX = x;
                          if (x > maxX) maxX = x;
                          if (y < minY) minY = y;
                          if (y > maxY) maxY = y;
                        }
                      }
                    }
                    if (maxX < 0 || maxY < 0) return null;
                    return { gray, w, h, minX, minY, maxX, maxY };
                  }

                  function renderQrAsciiFromCanvas(canvas) {
                    const meta = toGrayMatrix(canvas);
                    if (!meta) return null;
                    const { gray, w, minX, minY, maxX, maxY } = meta;
                    const qrW = maxX - minX + 1;
                    const qrH = maxY - minY + 1;
                    const size = Math.min(qrW, qrH);

                    // Prefer common QR module sizes where pixel/module is near an integer.
                    const candidates = [29, 33, 37, 41, 45, 49, 53, 57, 61, 65, 69];
                    let cols = 41;
                    let bestScore = Number.POSITIVE_INFINITY;
                    for (const c of candidates) {
                      const unit = size / c;
                      const rounded = Math.max(1, Math.round(unit));
                      const score = Math.abs(unit - rounded);
                      if (score < bestScore) {
                        bestScore = score;
                        cols = c;
                      }
                    }
                    const rows = cols;

                    const quiet = 4;
                    const lines = [];
                    const whiteLine = "  ".repeat(cols + quiet * 2);
                    for (let i = 0; i < quiet; i++) lines.push(whiteLine);

                    for (let r = 0; r < rows; r++) {
                      let line = "  ".repeat(quiet);
                      for (let c = 0; c < cols; c++) {
                        const sx = Math.min(maxX, minX + Math.floor(((c + 0.5) / cols) * qrW));
                        const sy = Math.min(maxY, minY + Math.floor(((r + 0.5) / rows) * qrH));
                        const isBlack = gray[sy * w + sx] < 128;
                        line += isBlack ? "██" : "  ";
                      }
                      line += "  ".repeat(quiet);
                      lines.push(line);
                    }
                    for (let i = 0; i < quiet; i++) lines.push(whiteLine);
                    return lines.join("\\n");
                  }

                  const imgCandidates = Array.from(document.querySelectorAll('img'))
                    .filter((img) => {
                      const src = String(img.getAttribute('src') || '');
                      const rect = img.getBoundingClientRect();
                      return rect.width >= 120 && rect.height >= 120 &&
                        (src.includes('qrImg') || src.toLowerCase().includes('qrcode') || src.toLowerCase().includes('qr'));
                    });

                  for (const img of imgCandidates) {
                    if (!img.naturalWidth || !img.naturalHeight) continue;
                    const c = document.createElement('canvas');
                    c.width = img.naturalWidth;
                    c.height = img.naturalHeight;
                    const ctx = c.getContext('2d');
                    if (!ctx) continue;
                    try {
                      ctx.drawImage(img, 0, 0);
                    } catch (_e) {
                      continue;
                    }
                    const art = renderQrAsciiFromCanvas(c);
                    if (art) return art;
                  }

                  const canvasCandidates = Array.from(document.querySelectorAll('canvas'))
                    .filter((cv) => cv.width >= 120 && cv.height >= 120);
                  for (const cv of canvasCandidates) {
                    const art = renderQrAsciiFromCanvas(cv);
                    if (art) return art;
                  }

                  return null;
                }"""
            )
        except Exception:
            return None

    def _is_expired(self, runtime: _QrLoginRuntimeSession) -> bool:
        return datetime.now(timezone.utc) >= runtime.expires_at

    def _probe_qr_authenticated(self, runtime: _QrLoginRuntimeSession) -> bool:
        try:
            current_url = str(runtime.page.url)
            if "loginSuccess" in current_url or "scan" in current_url:
                runtime.status = "scanned"
            if "jwxt.sysu.edu.cn" in current_url:
                runtime.status = "confirmed"
            latest_ticket_url = self._extract_latest_ticket_url(runtime)
            if latest_ticket_url is not None:
                runtime.latest_ticket_url = latest_ticket_url
            cookies = runtime.context.cookies()
            status_json = self._probe_upstream_status_with_cookies(cookies)
            authenticated = bool(status_json.get("data"))
            if authenticated:
                runtime.status = "success"
                return True

            if runtime.status == "confirmed":
                self._finalize_qr_sso(runtime)
                cookies = runtime.context.cookies()
                status_json = self._probe_upstream_status_with_cookies(cookies)
                authenticated = bool(status_json.get("data"))
                if authenticated:
                    runtime.status = "success"
            return authenticated
        except Exception as exc:
            runtime.last_error = str(exc)
            self._append_trace(runtime, event="error", url=str(runtime.page.url), error=str(exc))
            self._write_trace(runtime)
            return False

    def _finalize_qr_sso(self, runtime: _QrLoginRuntimeSession) -> None:
        service_url = self._student_service_url()
        cas_entry = (
            "https://cas.sysu.edu.cn/esc-sso/login"
            f"?service={service_url.replace(':', '%3A').replace('/', '%2F').replace('?', '%3F').replace('=', '%3D')}"
        )
        ticket_url = runtime.latest_ticket_url or self._extract_latest_ticket_url(runtime)
        try:
            req = runtime.context.request
            if ticket_url is None:
                bootstrap = req.get(
                    cas_entry,
                    timeout=20000,
                    max_redirects=0,
                    fail_on_status_code=False,
                    headers={"Referer": f"{settings.base_url}/#/login"},
                )
                self._append_trace(
                    runtime,
                    event="request",
                    url=cas_entry,
                    http_status=bootstrap.status,
                    location=bootstrap.headers.get("location"),
                )
                if bootstrap.status in {301, 302, 303, 307, 308}:
                    ticket_url = bootstrap.headers.get("location")
            if ticket_url:
                runtime.latest_ticket_url = ticket_url
                ticket_resp = req.get(ticket_url, timeout=20000, max_redirects=0, fail_on_status_code=False)
                self._append_api_response_trace(runtime, event="request", url=ticket_url, response=ticket_resp)
                redirect_url = ticket_resp.headers.get("location")
                if redirect_url:
                    redirect_resp = req.get(redirect_url, timeout=20000, max_redirects=0, fail_on_status_code=False)
                    self._append_api_response_trace(runtime, event="request", url=redirect_url, response=redirect_resp)
            self._hit_jwxt_post_login_endpoints(runtime)
        except Exception as exc:
            runtime.last_error = str(exc)
            self._append_trace(runtime, event="finalize_error", url=str(runtime.page.url), error=str(exc))

    def _hit_jwxt_post_login_endpoints(self, runtime: _QrLoginRuntimeSession) -> None:
        req = runtime.context.request
        targets = [
            f"{settings.base_url}/",
            f"{settings.base_url}/#/student",
            f"{settings.base_url}/api/privilege",
            f"{settings.base_url}/base-info/acadyearterm/showNewAcadlist",
            f"{settings.base_url}/api/login/status",
        ]
        for url in targets:
            try:
                if "/api/" in url or "/base-info/" in url:
                    response = req.get(
                        url,
                        timeout=20000,
                        fail_on_status_code=False,
                        headers=self._jwxt_ajax_headers(),
                    )
                    self._append_api_response_trace(runtime, event="request", url=url, response=response)
                else:
                    self._append_trace(runtime, event="goto", url=url)
                    runtime.page.goto(url, wait_until="domcontentloaded", timeout=20000)
                    runtime.page.wait_for_timeout(800)
                    self._append_trace(
                        runtime,
                        event="page_after_goto",
                        url=str(runtime.page.url),
                        cookies=self._summarize_cookie_names(runtime.context.cookies()),
                    )
            except Exception as exc:
                self._append_trace(runtime, event="request_error", url=url, error=str(exc))

    def _extract_latest_ticket_url(self, runtime: _QrLoginRuntimeSession) -> str | None:
        for item in reversed(runtime.redirect_trace):
            location = item.get("location")
            if isinstance(location, str) and "/api/sso/cas/login?ticket=" in location:
                return location
            url = item.get("url")
            if isinstance(url, str) and "/api/sso/cas/login?ticket=" in url:
                return url
        return None

    def _summarize_cookie_names(self, cookies: list[dict]) -> list[str]:
        summary = []
        for cookie in cookies:
            name = cookie.get("name")
            domain = cookie.get("domain")
            if name and domain:
                summary.append(f"{domain}:{name}")
        return sorted(summary)

    def _get_qr_runtime(self, login_session_id: str) -> _QrLoginRuntimeSession:
        self._cleanup_qr_sessions()
        with self._qr_lock:
            runtime = self._qr_sessions.get(login_session_id)
        if runtime is None:
            raise QrLoginSessionNotFoundError(f"QR login session {login_session_id} not found.")
        return runtime

    def _cleanup_qr_sessions(self) -> None:
        now = datetime.now(timezone.utc)
        with self._qr_lock:
            stale_ids = [sid for sid, rt in self._qr_sessions.items() if now >= rt.expires_at]
        for sid in stale_ids:
            try:
                runtime = self._qr_sessions.get(sid)
                if runtime is not None:
                    self._close_qr_session(runtime, reason="expired")
            except Exception:
                continue

    def _close_all_qr_sessions(self) -> None:
        with self._qr_lock:
            sessions = list(self._qr_sessions.values())
        for runtime in sessions:
            self._close_qr_session(runtime)

    def _close_qr_session(self, runtime: _QrLoginRuntimeSession, reason: str | None = None) -> None:
        if reason is not None:
            runtime.status = reason
        self._write_trace(runtime)
        with self._qr_lock:
            self._qr_sessions.pop(runtime.session_id, None)
        try:
            runtime.context.close()
        except Exception:
            pass
        try:
            runtime.browser.close()
        except Exception:
            pass
        try:
            runtime.playwright.stop()
        except Exception:
            pass

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

    def _persist_qr_runtime(self, runtime: _QrLoginRuntimeSession) -> None:
        if runtime.state_persisted:
            return
        runtime.context.storage_state(path=str(self._state_file))
        payload = json.loads(self._state_file.read_text(encoding="utf-8"))
        runtime.cookie_count = len(payload.get("cookies", []))
        runtime.state_persisted = True
        runtime.state_path = self._state_file
        self._append_trace(
            runtime,
            event="storage_state_persisted",
            url=str(runtime.page.url),
            cookie_count=runtime.cookie_count,
            state_path=str(self._state_file),
        )
        self._write_trace(runtime)

    def _attach_qr_trace_listeners(self, page: Page, redirect_trace: list[dict]) -> None:
        def on_response(response: Response) -> None:
            entry = {
                "timestamp": datetime.now(timezone.utc).isoformat(),
                "event": "response",
                "url": response.url,
                "status": response.status,
            }
            try:
                location = response.headers.get("location")
                if location:
                    entry["location"] = location
            except Exception:
                pass
            redirect_trace.append(entry)

        page.on("response", on_response)

    def _append_trace(self, runtime: _QrLoginRuntimeSession, event: str, url: str | None = None, **extra: object) -> None:
        entry = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "event": event,
            "status": runtime.status,
            "page_url": str(runtime.page.url),
            "cookie_count": len(runtime.context.cookies()),
        }
        if url is not None:
            entry["url"] = url
        entry.update(extra)
        runtime.redirect_trace.append(entry)

    def _append_api_response_trace(
        self,
        runtime: _QrLoginRuntimeSession,
        event: str,
        url: str,
        response: APIResponse,
    ) -> None:
        headers_subset = {}
        for key in ("location", "set-cookie", "content-type"):
            value = response.headers.get(key)
            if value:
                headers_subset[key] = value
        body_preview: str | None = None
        try:
            body_text = response.text()
            if body_text:
                body_preview = body_text[:600]
        except Exception:
            body_preview = None
        self._append_trace(
            runtime,
            event=event,
            url=url,
            http_status=response.status,
            headers=headers_subset or None,
            body_preview=body_preview,
            cookies=self._summarize_cookie_names(runtime.context.cookies()),
        )

    def _write_trace(self, runtime: _QrLoginRuntimeSession) -> None:
        if runtime.trace_path is None:
            return
        payload = {
            "login_session_id": runtime.session_id,
            "status": runtime.status,
            "expires_at": runtime.expires_at.isoformat(),
            "cas_login_url": runtime.cas_login_url,
            "wecom_iframe_url": runtime.wecom_iframe_url,
            "qr_page_url": runtime.qr_page_url,
            "qr_png_path": str(runtime.qr_png_path) if runtime.qr_png_path is not None else None,
            "state_persisted": runtime.state_persisted,
            "state_path": str(runtime.state_path) if runtime.state_path is not None else None,
            "cookie_count": runtime.cookie_count,
            "latest_ticket_url": runtime.latest_ticket_url,
            "last_error": runtime.last_error,
            "redirect_trace": runtime.redirect_trace,
        }
        runtime.trace_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
