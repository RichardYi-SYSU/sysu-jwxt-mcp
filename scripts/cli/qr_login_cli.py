from __future__ import annotations

import argparse
import base64
import json
import time
from pathlib import Path

import httpx


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Start JWXT QR login and render QR in terminal (ASCII)."
    )
    parser.add_argument("--api-base", default="http://127.0.0.1:8000")
    parser.add_argument("--interval-seconds", type=float, default=2.0)
    parser.add_argument("--timeout-seconds", type=float, default=60.0)
    parser.add_argument(
        "--save-qr-png",
        default="data/state/qr-login.png",
        help="Fallback path for saving qr_image_base64 when the API does not return qr_png_path.",
    )
    parser.add_argument(
        "--no-wait",
        action="store_true",
        help="Only start session and print QR, do not poll status.",
    )
    return parser.parse_args()


def _dump_json(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2)


def main() -> int:
    args = parse_args()
    base = args.api_base.rstrip("/")
    start_url = f"{base}/auth/qr/start"

    with httpx.Client(timeout=args.timeout_seconds) as client:
        start_resp = client.post(start_url)
        if start_resp.status_code >= 400:
            print(f"start failed: http={start_resp.status_code}")
            try:
                print(_dump_json(start_resp.json()))
            except Exception:
                print(start_resp.text)
            return 1
        payload = start_resp.json()

        session_id = payload["login_session_id"]
        print(f"login_session_id: {session_id}")
        print(f"status: {payload.get('status')}")
        print(f"expires_at: {payload.get('expires_at')}")
        if payload.get("qr_png_path"):
            print(f"qr_png_path: {payload['qr_png_path']}")

        qr_ascii = payload.get("qr_ascii")
        qr_b64 = payload.get("qr_image_base64")
        if qr_ascii:
            print("\n=== QR (ASCII) ===")
            print(qr_ascii)
        elif qr_b64:
            png_path = Path(args.save_qr_png)
            png_path.parent.mkdir(parents=True, exist_ok=True)
            png_path.write_bytes(base64.b64decode(qr_b64))
            print("\nASCII QR unavailable in this page variant.")
            print(f"Saved QR PNG: {png_path}")
        else:
            print("\nNo QR payload returned.")
            print(_dump_json(payload))

        if args.no_wait:
            return 0

        status_url = f"{base}/auth/qr/status"
        confirm_url = f"{base}/auth/qr/confirm"
        print("\nPolling status... press Ctrl+C to stop.")
        while True:
            status_resp = client.get(status_url, params={"login_session_id": session_id})
            status_resp.raise_for_status()
            status_payload = status_resp.json()
            status_value = status_payload.get("status")
            authenticated = status_payload.get("authenticated")
            print(f"status={status_value} authenticated={authenticated}")

            if status_value == "success":
                print("\n=== Success ===")
                print(_dump_json(status_payload))
                try:
                    confirm_resp = client.post(confirm_url, params={"login_session_id": session_id})
                    confirm_resp.raise_for_status()
                    print("\n=== Confirm (compatibility) ===")
                    print(_dump_json(confirm_resp.json()))
                except Exception:
                    pass
                return 0
            if status_value in {"expired", "failed"}:
                print("\n=== Ended ===")
                print(_dump_json(status_payload))
                return 1

            time.sleep(max(0.5, args.interval_seconds))


if __name__ == "__main__":
    raise SystemExit(main())
