from __future__ import annotations

import argparse
import json
import time
from datetime import datetime, timezone
from pathlib import Path

from playwright.sync_api import Page, sync_playwright


ROOT = Path(__file__).resolve().parent.parent
ARTIFACT_DIR = ROOT / "data" / "observation"
STATE_DIR = ROOT / "data" / "state"
BASE_URL = "https://jwxt.sysu.edu.cn/jwxt"


def now_slug() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Observe the SYSU JWXT login flow and save artifacts."
    )
    parser.add_argument(
        "--headed",
        action="store_true",
        help="Launch a visible browser window instead of the default headless mode.",
    )
    parser.add_argument(
        "--wait-seconds",
        type=int,
        default=20,
        help="How long to keep observing in headless mode before persisting artifacts.",
    )
    parser.add_argument(
        "--poll-seconds",
        type=float,
        default=2.0,
        help="How frequently to print the current page URL in headless mode.",
    )
    return parser.parse_args()


def install_network_logging(page: Page, request_log: list[dict], response_log: list[dict]) -> None:
    def on_request(request) -> None:
        request_log.append(
            {
                "method": request.method,
                "url": request.url,
                "resource_type": request.resource_type,
            }
        )

    def on_response(response) -> None:
        response_log.append(
            {
                "url": response.url,
                "status": response.status,
                "content_type": response.headers.get("content-type", ""),
            }
        )

    page.on("request", on_request)
    page.on("response", on_response)


def write_artifacts(
    *,
    run_id: str,
    page: Page,
    context,
    request_log: list[dict],
    response_log: list[dict],
) -> None:
    screenshot_path = ARTIFACT_DIR / f"login-page-{run_id}.png"
    html_path = ARTIFACT_DIR / f"login-page-{run_id}.html"
    request_path = ARTIFACT_DIR / f"requests-{run_id}.json"
    response_path = ARTIFACT_DIR / f"responses-{run_id}.json"
    state_path = STATE_DIR / "storage_state.json"

    page.screenshot(path=str(screenshot_path), full_page=True)
    html_path.write_text(page.content(), encoding="utf-8")
    context.storage_state(path=str(state_path))
    request_path.write_text(json.dumps(request_log, indent=2), encoding="utf-8")
    response_path.write_text(json.dumps(response_log, indent=2), encoding="utf-8")

    print(f"Saved screenshot to {screenshot_path}")
    print(f"Saved page HTML to {html_path}")
    print(f"Saved storage state to {state_path}")
    print(f"Saved request log to {request_path}")
    print(f"Saved response log to {response_path}")


def observe_headless(page: Page, wait_seconds: int, poll_seconds: float) -> None:
    deadline = time.monotonic() + wait_seconds
    last_url = ""

    print("Running in headless mode.")
    print("This mode is suitable for SSH-only environments.")
    print(
        "It records redirects, login pages, and network metadata, but it does not "
        "let you manually operate the remote browser."
    )

    while time.monotonic() < deadline:
        current_url = page.url
        if current_url != last_url:
            print(f"Current URL: {current_url}")
            last_url = current_url
        time.sleep(poll_seconds)

    print(f"Headless observation window finished after {wait_seconds} seconds.")


def observe_headed(page: Page) -> None:
    print("Opening JWXT in a visible browser window.")
    print("Complete the normal login flow and navigate to the timetable page.")
    input("After the browser is in the desired state, press Enter here to persist artifacts...")


def main() -> None:
    args = parse_args()
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    STATE_DIR.mkdir(parents=True, exist_ok=True)

    run_id = now_slug()
    request_log: list[dict] = []
    response_log: list[dict] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=not args.headed)
        context = browser.new_context()
        page = context.new_page()
        install_network_logging(page, request_log, response_log)

        print(f"Navigating to {BASE_URL}")
        page.goto(BASE_URL, wait_until="domcontentloaded")
        print(f"Initial URL: {page.url}")
        print(f"Initial title: {page.title()}")

        if args.headed:
            observe_headed(page)
        else:
            observe_headless(page, wait_seconds=args.wait_seconds, poll_seconds=args.poll_seconds)

        write_artifacts(
            run_id=run_id,
            page=page,
            context=context,
            request_log=request_log,
            response_log=response_log,
        )

        browser.close()


if __name__ == "__main__":
    main()
