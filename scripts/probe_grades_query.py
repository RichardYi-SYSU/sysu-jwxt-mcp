from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state" / "storage_state.json"
OUTPUT_PATH = ROOT / "data" / "observation" / "browser-fetched-grades.json"
START_URL = "https://jwxt.sysu.edu.cn/jwxt/#/student"


def main() -> None:
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)

    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        page.goto(START_URL, wait_until="networkidle", timeout=30000)
        payload = page.evaluate(
            """async () => {
                const headers = {
                  'X-Requested-With': 'XMLHttpRequest',
                  'Accept': 'application/json, text/plain, */*',
                  'moduleid': 'null',
                  'menuid': 'null',
                  'lastaccesstime': String(Date.now())
                };

                const doFetch = async (url) => {
                  const resp = await fetch(url, {
                    credentials: 'include',
                    headers
                  });
                  return {
                    status: resp.status,
                    body: await resp.text()
                  };
                };

                const academic = await doFetch('/jwxt/base-info/acadyearterm/showNewAcadlist?_t=' + Date.now());
                const academicJson = JSON.parse(academic.body);
                const term = academicJson.data.acadYearSemester;

                const listV2 = await doFetch('/jwxt/achievement-manage/score-check/listV2?semester=' + encodeURIComponent(term) + '&_t=' + Date.now());
                const creditSituation = await doFetch('/jwxt/achievement-manage/score-check/credit-situation?_t=' + Date.now());
                const pie = await doFetch('/jwxt/achievement-manage/score-check/getPicPie?_t=' + Date.now());

                return {
                  term,
                  academic,
                  listV2,
                  creditSituation,
                  pie
                };
            }"""
        )
        browser.close()

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved grade payloads to {OUTPUT_PATH}")
    print("term=", payload.get("term"))
    print("listV2 status=", payload.get("listV2", {}).get("status"))
    print(payload.get("listV2", {}).get("body", "")[:1200])


if __name__ == "__main__":
    main()
