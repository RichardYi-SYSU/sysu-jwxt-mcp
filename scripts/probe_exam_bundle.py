from __future__ import annotations

from pathlib import Path

from playwright.sync_api import sync_playwright


ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state" / "storage_state.json"
START_URL = "https://jwxt.sysu.edu.cn/jwxt/mk/#/stuExamInfo"
KEYWORDS = [
    "commonScheduleExamTime",
    "queryExamWeekName",
    "stuExamInfo",
    "examWeekId",
    "examDate",
    "examInfo",
    "queryUrl:",
    "outputUrl:",
    "getTableData=function",
    "changeTitle(",
    "query",
    "/schedule/",
]


def snippet(text: str, needle: str, radius: int = 500) -> str:
    index = text.find(needle)
    if index < 0:
        return ""
    start = max(0, index - radius)
    end = min(len(text), index + len(needle) + radius)
    return text[start:end]


def main() -> None:
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=True)
        context = browser.new_context(storage_state=str(STATE_PATH))
        page = context.new_page()
        page.goto(START_URL, wait_until="networkidle", timeout=30000)
        bundles = page.evaluate(
            """async () => {
                const scripts = Array.from(document.scripts)
                  .map((script) => script.src)
                  .filter(Boolean)
                  .filter((src) => src.includes('/assets/js/'));
                const uniq = Array.from(new Set(scripts));
                const outputs = [];
                for (const src of uniq) {
                  const resp = await fetch(src, { credentials: 'include' });
                  outputs.push({
                    src,
                    text: await resp.text()
                  });
                }
                return outputs;
            }"""
        )
        browser.close()

    for bundle in bundles:
        print(f"===== BUNDLE {bundle['src']} =====")
        for keyword in KEYWORDS:
            found = snippet(bundle["text"], keyword)
            print(f"----- {keyword} -----")
            if found:
                print(found)
            else:
                print("NOT_FOUND")


if __name__ == "__main__":
    main()
