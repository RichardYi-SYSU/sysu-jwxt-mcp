from __future__ import annotations

import json
from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state" / "storage_state.json"
START_URL = "https://jwxt.sysu.edu.cn/jwxt/mk/#/stuExamInfo"
OUTPUT_PATH = ROOT / "data" / "observation" / "browser-fetched-exams.json"


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
                  'lastaccesstime': String(Date.now()),
                  'Content-Type': 'application/json;charset=UTF-8'
                };
                const getJson = async (url) => {
                  const resp = await fetch(url, {
                    credentials: 'include',
                    headers
                  });
                  return {
                    status: resp.status,
                    body: await resp.text()
                  };
                };
                const postJson = async (url, body, params) => {
                  const fullUrl = new URL(url, window.location.origin);
                  Object.entries(params || {}).forEach(([key, value]) => fullUrl.searchParams.set(key, value));
                  const resp = await fetch(fullUrl.toString(), {
                    method: 'POST',
                    credentials: 'include',
                    headers,
                    body: JSON.stringify(body)
                  });
                  return {
                    status: resp.status,
                    body: await resp.text()
                  };
                };

                const acadResp = await getJson('/jwxt/base-info/acadyearterm/showNewAcadlist?_t=' + Date.now());
                const acadJson = JSON.parse(acadResp.body);
                const acadYear = acadJson.data.acadYearSemester;

                const examWeekResp = await getJson('/jwxt/schedule/agg/commonScheduleExamTime/queryExamWeekName?yearTerm=' + encodeURIComponent(acadYear) + '&_t=' + Date.now());
                const examWeekJson = JSON.parse(examWeekResp.body);
                const examWeeks = Array.isArray(examWeekJson.data) ? examWeekJson.data : [];
                const attempts = [];
                for (const examWeekObj of examWeeks) {
                  const queryBody = {
                    acadYear,
                    examWeekId: examWeekObj ? examWeekObj.examWeekId : null,
                    examDate: '',
                    examWeekName: examWeekObj ? (examWeekObj.examWeekName ?? examWeekObj.weekName ?? '') : '',
                    examWeekObj
                  };
                  const examsResp = await postJson(
                    '/jwxt/examination-manage/classroomResource/queryStuEaxmInfo',
                    queryBody,
                    { code: 'jwxsd_ksxxck' }
                  );
                  let parsed = null;
                  try {
                    parsed = JSON.parse(examsResp.body);
                  } catch (error) {
                    parsed = { parseError: String(error) };
                  }
                  attempts.push({
                    queryBody,
                    status: examsResp.status,
                    parsed
                  });
                }

                return {
                  academic: acadResp,
                  examWeeks: examWeekResp,
                  attempts
                };
            }"""
        )
        browser.close()

    OUTPUT_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"Saved exam payloads to {OUTPUT_PATH}")
    for attempt in payload["attempts"]:
        parsed = attempt["parsed"]
        size = len(parsed.get("data", [])) if isinstance(parsed, dict) and isinstance(parsed.get("data"), list) else "?"
        print(json.dumps(attempt["queryBody"], ensure_ascii=False, indent=2))
        print(f"status={attempt['status']} data_size={size}")


if __name__ == "__main__":
    main()
