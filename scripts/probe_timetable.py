from __future__ import annotations

import json
from pathlib import Path

import httpx


ROOT = Path(__file__).resolve().parent.parent
STATE_PATH = ROOT / "data" / "state" / "storage_state.json"
BASE_URL = "https://jwxt.sysu.edu.cn/jwxt"


def load_cookies() -> httpx.Cookies:
    jar = httpx.Cookies()
    payload = json.loads(STATE_PATH.read_text(encoding="utf-8"))
    for cookie in payload.get("cookies", []):
        jar.set(
            cookie["name"],
            cookie["value"],
            domain=cookie.get("domain"),
            path=cookie.get("path", "/"),
        )
    return jar


def main() -> None:
    cookies = load_cookies()
    with httpx.Client(cookies=cookies, timeout=20.0, follow_redirects=True) as client:
        academic_years = client.get(f"{BASE_URL}/base-info/acadyearterm/showNewAcadlist")
        student_table = client.get(f"{BASE_URL}/timetable-search/classTableInfo/selectStudentClassTable")

        print("=== acadyearterm ===")
        print(academic_years.status_code)
        print(academic_years.text[:2000])
        print("=== student timetable ===")
        print(student_table.status_code)
        print(student_table.text[:2000])


if __name__ == "__main__":
    main()
