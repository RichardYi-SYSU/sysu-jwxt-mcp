from __future__ import annotations

import random
import threading
from datetime import datetime, timezone

from sysu_jwxt_agent.schemas import KeepaliveStatus
from sysu_jwxt_agent.services.auth import AuthService


class SessionKeepaliveService:
    def __init__(
        self,
        auth_service: AuthService,
        interval_seconds: int = 300,
        jitter_seconds: int = 20,
    ) -> None:
        self._auth_service = auth_service
        self._interval_seconds = max(1, interval_seconds)
        self._jitter_seconds = max(0, jitter_seconds)
        self._enabled = True
        self._thread: threading.Thread | None = None
        self._stop_event = threading.Event()
        self._lock = threading.Lock()
        self._last_ok: bool | None = None
        self._last_checked_at: str | None = None
        self._last_error: str | None = None
        self._tick_count = 0
        self._consecutive_failures = 0

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
        with self._lock:
            last_ok = self._last_ok
            last_checked_at = self._last_checked_at
            last_error = self._last_error
            tick_count = self._tick_count
            consecutive_failures = self._consecutive_failures
        return KeepaliveStatus(
            enabled=self._enabled,
            interval_seconds=self._interval_seconds,
            jitter_seconds=self._jitter_seconds,
            running=running,
            authenticated=authenticated,
            last_ok=last_ok,
            last_checked_at=last_checked_at,
            last_error=last_error,
            tick_count=tick_count,
            consecutive_failures=consecutive_failures,
        )

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self._tick()
            self._stop_event.wait(self._next_wait_seconds())

    def _next_wait_seconds(self) -> float:
        if self._jitter_seconds <= 0:
            return float(self._interval_seconds)
        delta = random.uniform(-self._jitter_seconds, self._jitter_seconds)
        return max(1.0, float(self._interval_seconds) + delta)

    def _tick(self) -> None:
        now = datetime.now(timezone.utc).isoformat()
        try:
            ok = self._auth_service.keepalive_probe()
            error = None if ok else "keepalive_probe returned false"
        except Exception as exc:  # pragma: no cover - defensive for live runtime
            ok = False
            error = str(exc)

        with self._lock:
            self._tick_count += 1
            self._last_ok = ok
            self._last_error = error
            self._last_checked_at = now
            if ok:
                self._consecutive_failures = 0
            else:
                self._consecutive_failures += 1
