from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state" / "storage_state.json"
ARTIFACT_DIR = ROOT / "data" / "observation"
BASE_URL = "https://jwxt.sysu.edu.cn/jwxt"


def main() -> None:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        page.goto(f"{BASE_URL}/#/student", wait_until="networkidle", timeout=30000)

        result = page.evaluate(
            """async ({ baseUrl }) => {
                const opts = {
                  credentials: 'include',
                  headers: {
                    'X-Requested-With': 'XMLHttpRequest',
                    'Accept': 'application/json, text/plain, */*',
                    'moduleid': 'null',
                    'menuid': 'null',
                    'lastaccesstime': String(Date.now())
                  }
                };

                const academicResp = await fetch(`${baseUrl}/base-info/acadyearterm/showNewAcadlist?_t=${Date.now()}`, opts);
                const academicText = await academicResp.text();

                const weeklyResp = await fetch(`${baseUrl}/base-info/school-calender/weekly?academicYear=2025-2&_t=${Date.now()}`, opts);
                const weeklyText = await weeklyResp.text();

                const calendarResp = await fetch(`${baseUrl}/base-info/school-calender?academicYear=2025-2&weekly=5&_t=${Date.now()}`, opts);
                const calendarText = await calendarResp.text();

                const timetableResp = await fetch(`${baseUrl}/timetable-search/classTableInfo/selectStudentClassTable?academicYear=2025-2&weekly=5&_t=${Date.now()}`, opts);
                const timetableText = await timetableResp.text();

                return {
                  academic: { status: academicResp.status, body: academicText },
                  weekly: { status: weeklyResp.status, body: weeklyText },
                  calendar: { status: calendarResp.status, body: calendarText },
                  timetable: { status: timetableResp.status, body: timetableText }
                };
            }""",
            {"baseUrl": BASE_URL},
        )

        output_path = ARTIFACT_DIR / "browser-fetched-timetable.json"
        output_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
        print(json.dumps(result, ensure_ascii=False, indent=2)[:4000])
        print(f"Saved response bodies to {output_path}")
        browser.close()


if __name__ == "__main__":
    main()
