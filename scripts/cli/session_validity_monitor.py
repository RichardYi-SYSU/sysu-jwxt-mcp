from __future__ import annotations

import argparse
import json
import signal
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Periodically checks whether JWXT session is still authenticated."
    )
    parser.add_argument(
        "--api-base",
        default="http://127.0.0.1:8000",
        help="Base URL of local sysu-jwxt-agent API.",
    )
    parser.add_argument(
        "--interval-seconds",
        type=int,
        default=60,
        help="Polling interval in seconds.",
    )
    parser.add_argument(
        "--timeout-seconds",
        type=float,
        default=10.0,
        help="HTTP timeout in seconds.",
    )
    parser.add_argument(
        "--output",
        default="data/monitor/session-validity.log",
        help="Output JSONL log file path.",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=0,
        help="Stop after N checks. 0 means run forever.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    interval_seconds = max(1, args.interval_seconds)
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)

    stop = False

    def _handle_signal(signum, _frame) -> None:  # noqa: ANN001
        nonlocal stop
        stop = True
        print(f"\nreceived signal {signum}, stopping monitor...", flush=True)

    signal.signal(signal.SIGINT, _handle_signal)
    signal.signal(signal.SIGTERM, _handle_signal)

    refresh_url = args.api_base.rstrip("/") + "/auth/refresh"
    iteration = 0

    with httpx.Client(timeout=args.timeout_seconds) as client:
        while not stop:
            iteration += 1
            started = time.monotonic()
            ts = datetime.now(timezone.utc).isoformat()
            record: dict[str, object] = {
                "timestamp": ts,
                "url": refresh_url,
                "ok": False,
            }

            try:
                response = client.post(refresh_url)
                latency_ms = round((time.monotonic() - started) * 1000, 2)
                payload = response.json()
                authenticated = bool(payload.get("authenticated"))
                record.update(
                    {
                        "ok": response.status_code == 200 and authenticated,
                        "http_status": response.status_code,
                        "authenticated": authenticated,
                        "message": payload.get("message"),
                        "upstream_code": payload.get("upstream_code"),
                        "latency_ms": latency_ms,
                    }
                )
            except Exception as exc:  # pragma: no cover - runtime/network path
                latency_ms = round((time.monotonic() - started) * 1000, 2)
                record.update(
                    {
                        "error": str(exc),
                        "latency_ms": latency_ms,
                    }
                )

            with output_path.open("a", encoding="utf-8") as fp:
                fp.write(json.dumps(record, ensure_ascii=False) + "\n")

            status_text = "VALID" if record.get("ok") else "INVALID"
            print(
                f"[{record['timestamp']}] {status_text} "
                f"http={record.get('http_status')} auth={record.get('authenticated')} "
                f"latency={record.get('latency_ms')}ms",
                flush=True,
            )

            if args.max_iterations > 0 and iteration >= args.max_iterations:
                break

            if not stop:
                time.sleep(interval_seconds)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
