from __future__ import annotations

import threading
import time
from datetime import datetime, timezone

from sysu_jwxt_agent.schemas import KeepaliveStatus
from sysu_jwxt_agent.services.auth import AuthService


class SessionKeepaliveService:
    def __init__(self, auth_service: AuthService, interval_seconds: int = 120) -> None:
        self._auth_service = auth_service
        self._interval_seconds = interval_seconds
        self._enabled = True
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_ok: bool | None = None
        self._last_checked_at: str | None = None
        self._last_error: str | None = None

    def start(self) -> KeepaliveStatus:
        with self._lock:
            if self._thread is not None and self._thread.is_alive():
                return self.status()
            self._stop_event.clear()
            self._thread = threading.Thread(target=self._run, name="jwxt-keepalive", daemon=True)
            self._thread.start()
        return self.status()

    def stop(self) -> KeepaliveStatus:
        with self._lock:
            self._stop_event.set()
            thread = self._thread
            self._thread = None
        if thread is not None:
            thread.join(timeout=1.0)
        return self.status()

    def ping_once(self) -> KeepaliveStatus:
        self._tick()
        return self.status()

    def status(self) -> KeepaliveStatus:
        running = bool(self._thread is not None and self._thread.is_alive())
        authenticated: bool | None
        try:
            authenticated = self._auth_service.is_authenticated()
        except Exception:  # pragma: no cover - live network failures
            authenticated = None
        return KeepaliveStatus(
            enabled=self._enabled,
            interval_seconds=self._interval_seconds,
            running=running,
            authenticated=authenticated,
            last_ok=self._last_ok,
            last_checked_at=self._last_checked_at,
            last_error=self._last_error,
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(self._interval_seconds)

    def _tick(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        try:
            ok = self._auth_service.keepalive_probe()
            self._last_ok = ok
            self._last_error = None if ok else "keepalive_probe returned false"
        except Exception as exc:  # pragma: no cover - defensive for live runtime
            self._last_ok = False
            self._last_error = str(exc)
        self._last_checked_at = now
        time.sleep(0.01)
