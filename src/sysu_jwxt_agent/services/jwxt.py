import json
from collections import defaultdict

from playwright.sync_api import sync_playwright

from sysu_jwxt_agent.config import settings
from sysu_jwxt_agent.schemas import (
    ExamEntry,
    ExamsResponse,
    ExamWeek,
    GradeEntry,
    GradesResponse,
    TimetableEntry,
    TimetableResponse,
)
from sysu_jwxt_agent.services.auth import AuthService
from sysu_jwxt_agent.services.browser import BrowserSessionManager
from sysu_jwxt_agent.services.cache import TimetableCache


class AuthenticationRequiredError(RuntimeError):
    pass


class UpstreamNotImplementedError(RuntimeError):
    pass


class InvalidQueryError(RuntimeError):
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

    def get_timetable(self, term: str, include_raw: bool = False) -> TimetableResponse:
        if not self._auth_service.is_authenticated():
            raise AuthenticationRequiredError("No authenticated session is available.")

        try:
            timetable = self._fetch_live_timetable(term, include_raw=include_raw)
            self._cache.save(timetable)
            return self._to_agent_timetable(timetable, include_raw=include_raw)
        except Exception:
            cached = self._cache.load(term)
            if cached is not None:
                return self._to_agent_timetable(cached, include_raw=include_raw)
            raise

    def get_exams(
        self,
        term: str,
        exam_week_id: str | None = None,
        include_raw: bool = False,
    ) -> ExamsResponse:
        if not self._auth_service.is_authenticated():
            raise AuthenticationRequiredError("No authenticated session is available.")

        exams = self._fetch_live_exams(term=term, exam_week_id=exam_week_id, include_raw=include_raw)
        return self._to_agent_exams(exams, include_raw=include_raw)

    def get_grades(self, term: str, include_raw: bool = False) -> GradesResponse:
        if not self._auth_service.is_authenticated():
            raise AuthenticationRequiredError("No authenticated session is available.")

        grades = self._fetch_live_grades(term=term, include_raw=include_raw)
        return self._to_agent_grades(grades, include_raw=include_raw)

    def _fetch_live_timetable(self, term: str, include_raw: bool) -> TimetableResponse:
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
            include_raw=include_raw,
        )
        return TimetableResponse(
            term=payload["academicYear"],
            stale=False,
            source="live",
            entries=entries,
        )

    def _fetch_live_exams(self, term: str, exam_week_id: str | None, include_raw: bool) -> ExamsResponse:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(self._browser_manager.storage_state_path)
            )
            page = context.new_page()
            page.goto(f"{settings.base_url}/mk/#/stuExamInfo", wait_until="networkidle", timeout=30000)

            payload = page.evaluate(
                """async ({ baseUrl, requestedTerm, requestedExamWeekId }) => {
                    const mkHeaders = (jsonBody = false) => {
                      const headers = {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json, text/plain, */*',
                        'moduleid': 'null',
                        'menuid': 'null',
                        'lastaccesstime': String(Date.now())
                      };
                      if (jsonBody) {
                        headers['Content-Type'] = 'application/json;charset=UTF-8';
                      }
                      return headers;
                    };
                    const doFetch = async (url, options = {}) => {
                      const resp = await fetch(url, {
                        credentials: 'include',
                        ...options
                      });
                      const text = await resp.text();
                      return { status: resp.status, text };
                    };

                    const academic = await doFetch(`${baseUrl}/base-info/acadyearterm/showNewAcadlist?_t=${Date.now()}`, {
                      headers: mkHeaders()
                    });
                    const academicJson = JSON.parse(academic.text);
                    const academicYear = requestedTerm === 'current'
                      ? academicJson.data.acadYearSemester
                      : requestedTerm;

                    const examWeeksResponse = await doFetch(
                      `${baseUrl}/schedule/agg/commonScheduleExamTime/queryExamWeekName?yearTerm=${encodeURIComponent(academicYear)}&_t=${Date.now()}`,
                      { headers: mkHeaders() }
                    );
                    const examWeeksJson = JSON.parse(examWeeksResponse.text);
                    const examWeeks = Array.isArray(examWeeksJson.data) ? examWeeksJson.data : [];
                    const targetWeeks = requestedExamWeekId
                      ? examWeeks.filter((week) => week.examWeekId === requestedExamWeekId)
                      : examWeeks;

                    const attempts = [];
                    for (const examWeekObj of targetWeeks) {
                      const queryBody = {
                        acadYear: academicYear,
                        examWeekId: examWeekObj ? examWeekObj.examWeekId : null,
                        examDate: '',
                        examWeekName: examWeekObj ? (examWeekObj.examWeekName ?? examWeekObj.weekName ?? '') : '',
                        examWeekObj
                      };
                      const exams = await doFetch(
                        `${baseUrl}/examination-manage/classroomResource/queryStuEaxmInfo?code=jwxsd_ksxxck`,
                        {
                          method: 'POST',
                          headers: mkHeaders(true),
                          body: JSON.stringify(queryBody)
                        }
                      );
                      attempts.push({
                        queryBody,
                        exams
                      });
                    }

                    return {
                      academicYear,
                      examWeeks,
                      attempts
                    };
                }""",
                {
                    "baseUrl": settings.base_url,
                    "requestedTerm": term,
                    "requestedExamWeekId": exam_week_id,
                },
            )
            browser.close()

        exam_weeks = [self._build_exam_week(item) for item in payload.get("examWeeks", [])]
        if exam_week_id and not payload.get("attempts"):
            raise InvalidQueryError(f"Exam week {exam_week_id} was not found for term {payload['academicYear']}.")

        attempts = []
        for attempt in payload.get("attempts", []):
            response = attempt["exams"]
            if response["status"] != 200:
                raise UpstreamNotImplementedError(
                    f"Exam endpoint returned unexpected status {response['status']}."
                )
            attempts.append(
                {
                    "query": attempt["queryBody"],
                    "parsed": json.loads(response["text"]),
                }
            )

        selected_attempt = next(
            (
                attempt
                for attempt in attempts
                if isinstance(attempt["parsed"].get("data"), list) and attempt["parsed"]["data"]
            ),
            attempts[0] if attempts else None,
        )
        selected_exam_week = None
        raw_records: list[dict] = []
        entries: list[ExamEntry] = []

        if selected_attempt is not None:
            raw_records = selected_attempt["parsed"].get("data", [])
            selected_exam_week = self._build_exam_week(selected_attempt["query"]["examWeekObj"])
            entries = self._parse_exam_entries(
                term=payload["academicYear"],
                selected_exam_week=selected_exam_week,
                rows=raw_records,
                include_raw=include_raw,
            )

        return ExamsResponse(
            term=payload["academicYear"],
            stale=False,
            source="live",
            selected_exam_week=selected_exam_week,
            exam_weeks=exam_weeks,
            entries=entries,
            raw_records=raw_records if include_raw else None,
        )

    def _fetch_live_grades(self, term: str, include_raw: bool) -> GradesResponse:
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

                    const listV2 = await doFetch(`${baseUrl}/achievement-manage/score-check/listV2?semester=${encodeURIComponent(academicYear)}&_t=${Date.now()}`);
                    const creditSituation = await doFetch(`${baseUrl}/achievement-manage/score-check/credit-situation?_t=${Date.now()}`);
                    const pie = await doFetch(`${baseUrl}/achievement-manage/score-check/getPicPie?_t=${Date.now()}`);

                    return {
                      academicYear,
                      listV2,
                      creditSituation,
                      pie
                    };
                }""",
                {"baseUrl": settings.base_url, "requestedTerm": term},
            )
            browser.close()

        if payload["listV2"]["status"] != 200:
            raise UpstreamNotImplementedError(
                f"Grades endpoint returned unexpected status {payload['listV2']['status']}."
            )
        if payload["creditSituation"]["status"] != 200:
            raise UpstreamNotImplementedError(
                "Grades summary endpoint returned unexpected status "
                f"{payload['creditSituation']['status']}."
            )
        if payload["pie"]["status"] != 200:
            raise UpstreamNotImplementedError(
                f"Grades distribution endpoint returned unexpected status {payload['pie']['status']}."
            )

        list_json = json.loads(payload["listV2"]["text"])
        credit_json = json.loads(payload["creditSituation"]["text"])
        pie_json = json.loads(payload["pie"]["text"])

        rows = list_json.get("data", [])
        if not isinstance(rows, list):
            rows = []

        entries = self._parse_grade_entries(
            term=payload["academicYear"],
            rows=rows,
            include_raw=include_raw,
        )

        summary = credit_json.get("data", {})
        if not isinstance(summary, dict):
            summary = {}

        distribution = pie_json.get("data", [])
        if not isinstance(distribution, list):
            distribution = []

        return GradesResponse(
            term=payload["academicYear"],
            stale=False,
            source="live",
            entries=entries,
            summary=summary,
            distribution=distribution,
            raw_records=rows if include_raw else None,
        )

    def _parse_timetable_entries(
        self,
        *,
        term: str,
        week: int,
        rows: list[dict],
        include_raw: bool,
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
                            "raw_source": (
                                {
                                    "row": row,
                                    "field": field,
                                    "block": block,
                                }
                                if include_raw
                                else None
                            ),
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
                        raw_source={"segments": raw_sources} if include_raw else None,
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

    def _build_exam_week(self, payload: dict | None) -> ExamWeek | None:
        if not payload:
            return None
        return ExamWeek(
            exam_week_id=payload["examWeekId"],
            exam_week_name=payload["examWeekName"],
            start_date=payload.get("startDate"),
            end_date=payload.get("endDate"),
            apply_range=payload.get("applyRange"),
        )

    def _parse_exam_entries(
        self,
        *,
        term: str,
        selected_exam_week: ExamWeek | None,
        rows: list[dict],
        include_raw: bool,
    ) -> list[ExamEntry]:
        entries: list[ExamEntry] = []

        for row_index, row in enumerate(rows):
            timetable = row.get("timetable")
            if not isinstance(timetable, dict):
                continue

            section_label = str(row.get("dataNumber") or row_index + 1)
            for weekday_key, cells in timetable.items():
                try:
                    weekday = int(weekday_key)
                except (TypeError, ValueError):
                    weekday = None

                if not isinstance(cells, list):
                    continue

                for cell_index, cell in enumerate(cells):
                    if not isinstance(cell, dict) or cell.get("emptyFlag"):
                        continue

                    duration_minutes = None
                    duration = cell.get("duration")
                    if duration not in {None, ""}:
                        try:
                            duration_minutes = int(duration)
                        except (TypeError, ValueError):
                            duration_minutes = None

                    entries.append(
                        ExamEntry(
                            term=term,
                            exam_week_id=selected_exam_week.exam_week_id if selected_exam_week else None,
                            exam_week_name=selected_exam_week.exam_week_name if selected_exam_week else None,
                            course_name=cell.get("examSubjectName") or cell.get("courseName"),
                            exam_date=cell.get("examDate"),
                            exam_time=cell.get("durationTime") or cell.get("startTime"),
                            duration_minutes=duration_minutes,
                            location=cell.get("classroomNumber"),
                            exam_stage=cell.get("examStage"),
                            exam_mode=cell.get("examMode"),
                            weekday=weekday if weekday in WEEKDAY_FIELDS else None,
                            section_label=section_label,
                            raw_source=(
                                {
                                    "row_index": row_index,
                                    "cell_index": cell_index,
                                    "cell": cell,
                                }
                                if include_raw
                                else None
                            ),
                        )
                    )

        return sorted(
            entries,
            key=lambda entry: (
                entry.exam_date or "",
                entry.weekday or 0,
                entry.section_label or "",
                entry.course_name or "",
            ),
        )

    def _parse_grade_entries(
        self,
        *,
        term: str,
        rows: list[dict],
        include_raw: bool,
    ) -> list[GradeEntry]:
        entries: list[GradeEntry] = []

        for row in rows:
            if not isinstance(row, dict):
                continue
            entries.append(
                GradeEntry(
                    term=term,
                    course_name=self._first_non_empty(
                        row,
                        ["courseName", "course_name", "kcName", "kcmc"],
                    ),
                    course_code=self._first_non_empty(
                        row,
                        ["courseNo", "courseCode", "kch"],
                    ),
                    course_type=self._first_non_empty(
                        row,
                        ["courseAttributeName", "courseType", "kclb"],
                    ),
                    credit=self._as_float(
                        self._first_non_empty(
                            row,
                            ["credit", "courseCredit", "xf"],
                        )
                    ),
                    score=self._first_non_empty(
                        row,
                        ["score", "scoreValue", "achievement", "cj"],
                    ),
                    grade_point=self._as_float(
                        self._first_non_empty(
                            row,
                            ["gradePoint", "grade_point", "point", "jd"],
                        )
                    ),
                    exam_nature=self._first_non_empty(
                        row,
                        ["examNature", "examType", "ksxz"],
                    ),
                    assessment_method=self._first_non_empty(
                        row,
                        ["assessmentMethod", "assessmentType", "khfs"],
                    ),
                    score_flag=self._first_non_empty(
                        row,
                        ["scoreFlag", "scoreSign", "cjbz"],
                    ),
                    raw_source=row if include_raw else None,
                )
            )

        return sorted(
            entries,
            key=lambda entry: (
                entry.course_name or "",
                entry.course_code or "",
            ),
        )

    def _to_agent_timetable(
        self,
        timetable: TimetableResponse,
        *,
        include_raw: bool,
    ) -> TimetableResponse:
        if include_raw:
            return timetable

        entries = []
        for entry in timetable.entries:
            cleaned = entry.model_copy(deep=True)
            cleaned.raw_source = None
            entries.append(cleaned)

        return TimetableResponse(
            term=timetable.term,
            stale=timetable.stale,
            source=timetable.source,
            entries=entries,
        )

    def _to_agent_exams(
        self,
        exams: ExamsResponse,
        *,
        include_raw: bool,
    ) -> ExamsResponse:
        if include_raw:
            return exams

        entries = []
        for entry in exams.entries:
            cleaned = entry.model_copy(deep=True)
            cleaned.raw_source = None
            entries.append(cleaned)

        return ExamsResponse(
            term=exams.term,
            stale=exams.stale,
            source=exams.source,
            selected_exam_week=exams.selected_exam_week,
            exam_weeks=exams.exam_weeks,
            entries=entries,
            raw_records=None,
        )

    def _to_agent_grades(
        self,
        grades: GradesResponse,
        *,
        include_raw: bool,
    ) -> GradesResponse:
        if include_raw:
            return grades

        entries = []
        for entry in grades.entries:
            cleaned = entry.model_copy(deep=True)
            cleaned.raw_source = None
            entries.append(cleaned)

        return GradesResponse(
            term=grades.term,
            stale=grades.stale,
            source=grades.source,
            entries=entries,
            summary=grades.summary,
            distribution=grades.distribution,
            raw_records=None,
        )

    def _first_non_empty(self, payload: dict, keys: list[str]) -> str | None:
        for key in keys:
            value = payload.get(key)
            if value in {None, ""}:
                continue
            return str(value)
        return None

    def _as_float(self, value: str | None) -> float | None:
        if value in {None, ""}:
            return None
        try:
            return float(value)
        except (TypeError, ValueError):
            return None
