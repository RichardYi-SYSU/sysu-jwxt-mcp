import json
from collections import defaultdict

from playwright.sync_api import sync_playwright

from sysu_jwxt_agent.config import settings
from sysu_jwxt_agent.schemas import TimetableEntry, TimetableResponse
from sysu_jwxt_agent.services.auth import AuthService
from sysu_jwxt_agent.services.browser import BrowserSessionManager
from sysu_jwxt_agent.services.cache import TimetableCache


class AuthenticationRequiredError(RuntimeError):
    pass


class UpstreamNotImplementedError(RuntimeError):
    pass


WEEKDAY_FIELDS = {
    1: "monday",
    2: "tuesday",
    3: "wednesday",
    4: "thursday",
    5: "friday",
    6: "saturday",
    7: "sunday",
}


class JwxtClient:
    def __init__(
        self,
        auth_service: AuthService,
        cache: TimetableCache,
        browser_manager: BrowserSessionManager,
    ) -> None:
        self._auth_service = auth_service
        self._cache = cache
        self._browser_manager = browser_manager

    def get_timetable(self, term: str) -> TimetableResponse:
        if not self._auth_service.is_authenticated():
            raise AuthenticationRequiredError("No authenticated session is available.")

        try:
            timetable = self._fetch_live_timetable(term)
            self._cache.save(timetable)
            return timetable
        except Exception:
            cached = self._cache.load(term)
            if cached is not None:
                return cached
            raise

    def _fetch_live_timetable(self, term: str) -> TimetableResponse:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(self._browser_manager.storage_state_path)
            )
            page = context.new_page()
            page.goto(f"{settings.base_url}/#/student", wait_until="networkidle", timeout=30000)

            payload = page.evaluate(
                """async ({ baseUrl, requestedTerm }) => {
                    const mkHeaders = () => ({
                      'X-Requested-With': 'XMLHttpRequest',
                      'Accept': 'application/json, text/plain, */*',
                      'moduleid': 'null',
                      'menuid': 'null',
                      'lastaccesstime': String(Date.now())
                    });
                    const doFetch = async (url) => {
                      const resp = await fetch(url, {
                        credentials: 'include',
                        headers: mkHeaders()
                      });
                      const text = await resp.text();
                      return { status: resp.status, text };
                    };

                    const academic = await doFetch(`${baseUrl}/base-info/acadyearterm/showNewAcadlist?_t=${Date.now()}`);
                    const academicJson = JSON.parse(academic.text);
                    const academicYear = requestedTerm === 'current'
                      ? academicJson.data.acadYearSemester
                      : requestedTerm;

                    const weekly = await doFetch(`${baseUrl}/base-info/school-calender/weekly?academicYear=${encodeURIComponent(academicYear)}&_t=${Date.now()}`);
                    const weeklyJson = JSON.parse(weekly.text);
                    const currentWeek = weeklyJson.data.nowTimeWeekly ?? weeklyJson.data.nowWeekly;

                    const calendar = await doFetch(`${baseUrl}/base-info/school-calender?academicYear=${encodeURIComponent(academicYear)}&weekly=${encodeURIComponent(currentWeek)}&_t=${Date.now()}`);
                    const timetable = await doFetch(`${baseUrl}/timetable-search/classTableInfo/selectStudentClassTable?academicYear=${encodeURIComponent(academicYear)}&weekly=${encodeURIComponent(currentWeek)}&_t=${Date.now()}`);

                    return {
                      academicYear,
                      currentWeek: Number(currentWeek),
                      academic,
                      weekly,
                      calendar,
                      timetable
                    };
                }""",
                {"baseUrl": settings.base_url, "requestedTerm": term},
            )
            browser.close()

        timetable_status = payload["timetable"]["status"]
        if timetable_status != 200:
            raise UpstreamNotImplementedError(
                f"Timetable endpoint returned unexpected status {timetable_status}."
            )

        timetable_json = json.loads(payload["timetable"]["text"])
        entries = self._parse_timetable_entries(
            term=payload["academicYear"],
            week=payload["currentWeek"],
            rows=timetable_json.get("data", []),
        )
        return TimetableResponse(
            term=payload["academicYear"],
            stale=False,
            source="live",
            entries=entries,
        )

    def _parse_timetable_entries(
        self,
        *,
        term: str,
        week: int,
        rows: list[dict],
    ) -> list[TimetableEntry]:
        parsed_items: list[dict] = []

        for row in rows:
            section = int(row["section"])
            for weekday, field in WEEKDAY_FIELDS.items():
                raw_value = row.get(field)
                if not raw_value:
                    continue
                for block in raw_value.split(",,"):
                    parts = block.split(";;")
                    if not parts or not parts[0].strip():
                        continue
                    course_name = parts[0].strip()
                    teacher = parts[1].strip() or None if len(parts) > 1 else None
                    location = parts[2].strip() or None if len(parts) > 2 else None
                    parsed_items.append(
                        {
                            "term": term,
                            "weekday": weekday,
                            "section": section,
                            "course_name": course_name,
                            "teacher": teacher,
                            "location": location,
                            "week": week,
                            "raw_source": {
                                "row": row,
                                "field": field,
                                "block": block,
                            },
                        }
                    )

        grouped: dict[tuple, list[dict]] = defaultdict(list)
        for item in parsed_items:
            key = (
                item["term"],
                item["weekday"],
                item["course_name"],
                item["teacher"],
                item["location"],
            )
            grouped[key].append(item)

        entries: list[TimetableEntry] = []
        for (entry_term, weekday, course_name, teacher, location), items in grouped.items():
            ordered = sorted(items, key=lambda item: item["section"])
            start = ordered[0]["section"]
            end = ordered[0]["section"]
            raw_sources = [ordered[0]["raw_source"]]

            def flush() -> None:
                entries.append(
                    TimetableEntry(
                        term=entry_term,
                        course_name=course_name,
                        teacher=teacher,
                        weekday=weekday,
                        start_section=start,
                        end_section=end,
                        weeks=[ordered[0]["week"]],
                        location=location,
                        raw_source={"segments": raw_sources},
                    )
                )

            for item in ordered[1:]:
                if item["section"] == end + 1:
                    end = item["section"]
                    raw_sources.append(item["raw_source"])
                else:
                    flush()
                    start = item["section"]
                    end = item["section"]
                    raw_sources = [item["raw_source"]]
            flush()

        return sorted(
            entries,
            key=lambda entry: (entry.weekday, entry.start_section, entry.course_name),
        )
