from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state" / "storage_state.json"
ARTIFACT_DIR = ROOT / "data" / "observation"
START_URL = "https://jwxt.sysu.edu.cn/jwxt/#/student"


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    request_log: list[dict] = []
    response_log: list[dict] = []

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()

        page.on(
            "request",
            lambda request: request_log.append(
                {
                    "method": request.method,
                    "url": request.url,
                    "resource_type": request.resource_type,
                    "headers": request.headers,
                }
            ),
        )
        page.on(
            "response",
            lambda response: response_log.append(
                {
                    "url": response.url,
                    "status": response.status,
                    "headers": response.headers,
                }
            ),
        )

        page.goto(START_URL, wait_until="networkidle", timeout=30000)
        screenshot_path = ARTIFACT_DIR / "student-page-authenticated.png"
        html_path = ARTIFACT_DIR / "student-page-authenticated.html"
        requests_path = ARTIFACT_DIR / "student-page-authenticated-requests.json"
        responses_path = ARTIFACT_DIR / "student-page-authenticated-responses.json"

        page.screenshot(path=str(screenshot_path), full_page=True)
        html_path.write_text(page.content(), encoding="utf-8")
        requests_path.write_text(json.dumps(request_log, ensure_ascii=False, indent=2), encoding="utf-8")
        responses_path.write_text(json.dumps(response_log, ensure_ascii=False, indent=2), encoding="utf-8")

        print(page.url)
        print(page.title())
        print(f"Saved screenshot to {screenshot_path}")
        print(f"Saved HTML to {html_path}")
        print(f"Saved requests to {requests_path}")
        print(f"Saved responses to {responses_path}")

        browser.close()


if __name__ == "__main__":
    main()
