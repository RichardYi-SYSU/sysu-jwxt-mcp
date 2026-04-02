import json
import re
from collections import defaultdict

from playwright.sync_api import sync_playwright

from sysu_jwxt_agent.config import settings
from sysu_jwxt_agent.schemas import (
    CetScoreEntry,
    CetScoresResponse,
    EmptyClassroomEntry,
    EmptyClassroomsResponse,
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

SECTION_FIELDS: list[tuple[int, str]] = [
    (1, "oneSection"),
    (2, "twoSection"),
    (3, "threeSection"),
    (4, "fourSection"),
    (5, "fiveSection"),
    (6, "sixSection"),
    (7, "sevenSection"),
    (8, "eightSection"),
    (9, "nineSection"),
    (10, "tenSection"),
    (11, "elevenSection"),
    (12, "twelveSection"),
    (13, "thirteenSection"),
    (14, "fourteenSection"),
    (15, "fifteenSection"),
    (16, "sixteenSection"),
]


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

    def get_timetable(
        self,
        term: str,
        week: int | None = None,
        include_raw: bool = False,
    ) -> TimetableResponse:
        if not self._auth_service.is_authenticated():
            raise AuthenticationRequiredError("No authenticated session is available.")

        try:
            timetable = self._fetch_live_timetable(term=term, week=week, include_raw=include_raw)
            self._cache.save(timetable)
            return self._to_agent_timetable(timetable, include_raw=include_raw)
        except Exception:
            cached = self._cache.load(term=term, week=week)
            if cached is not None:
                return self._to_agent_timetable(cached, include_raw=include_raw)
            raise

    def get_exams(
        self,
        term: str,
        exam_week_id: str | None = None,
        exam_week_type: str | None = None,
        include_raw: bool = False,
    ) -> ExamsResponse:
        if not self._auth_service.is_authenticated():
            raise AuthenticationRequiredError("No authenticated session is available.")

        exams = self._fetch_live_exams(
            term=term,
            exam_week_id=exam_week_id,
            exam_week_type=exam_week_type,
            include_raw=include_raw,
        )
        return self._to_agent_exams(exams, include_raw=include_raw)

    def get_grades(self, term: str, include_raw: bool = False) -> GradesResponse:
        if not self._auth_service.is_authenticated():
            raise AuthenticationRequiredError("No authenticated session is available.")

        grades = self._fetch_live_grades(term=term, include_raw=include_raw)
        return self._to_agent_grades(grades, include_raw=include_raw)

    def get_cet_scores(self, *, level: int, include_raw: bool = False) -> CetScoresResponse:
        if not self._auth_service.is_authenticated():
            raise AuthenticationRequiredError("No authenticated session is available.")
        return self._fetch_live_cet_scores(level=level, include_raw=include_raw)

    def get_empty_classrooms(
        self,
        *,
        date_value: str,
        campus: str,
        section_range: str,
        include_raw: bool = False,
    ) -> EmptyClassroomsResponse:
        if not self._auth_service.is_authenticated():
            raise AuthenticationRequiredError("No authenticated session is available.")

        section_start, section_end = self._parse_section_range(section_range)
        classrooms = self._fetch_live_empty_classrooms(
            date_value=date_value,
            campus=campus,
            section_range=section_range,
            section_start=section_start,
            section_end=section_end,
            include_raw=include_raw,
        )
        return self._to_agent_empty_classrooms(classrooms, include_raw=include_raw)

    def _fetch_live_timetable(self, term: str, week: int | None, include_raw: bool) -> TimetableResponse:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(self._browser_manager.storage_state_path)
            )
            page = context.new_page()
            page.goto(f"{settings.base_url}/#/student", wait_until="networkidle", timeout=30000)

            payload = page.evaluate(
                """async ({ baseUrl, requestedTerm, requestedWeek }) => {
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
                    const currentWeek = Number(weeklyJson.data.nowTimeWeekly ?? weeklyJson.data.nowWeekly);
                    const selectedWeek = Number(requestedWeek || currentWeek);

                    const calendar = await doFetch(`${baseUrl}/base-info/school-calender?academicYear=${encodeURIComponent(academicYear)}&weekly=${encodeURIComponent(selectedWeek)}&_t=${Date.now()}`);
                    const timetable = await doFetch(`${baseUrl}/timetable-search/classTableInfo/selectStudentClassTable?academicYear=${encodeURIComponent(academicYear)}&weekly=${encodeURIComponent(selectedWeek)}&_t=${Date.now()}`);

                    return {
                      academicYear,
                      currentWeek,
                      selectedWeek,
                      academic,
                      weekly,
                      calendar,
                      timetable
                    };
                }""",
                {
                    "baseUrl": settings.base_url,
                    "requestedTerm": term,
                    "requestedWeek": week,
                },
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
            week=payload["selectedWeek"],
            rows=timetable_json.get("data", []),
            include_raw=include_raw,
        )
        return TimetableResponse(
            term=payload["academicYear"],
            week=payload["selectedWeek"],
            stale=False,
            source="live",
            entries=entries,
        )

    def _fetch_live_exams(
        self,
        term: str,
        exam_week_id: str | None,
        exam_week_type: str | None,
        include_raw: bool,
    ) -> ExamsResponse:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(self._browser_manager.storage_state_path)
            )
            page = context.new_page()
            page.goto(f"{settings.base_url}/mk/#/stuExamInfo", wait_until="networkidle", timeout=30000)

            payload = page.evaluate(
                """async ({ baseUrl, requestedTerm, requestedExamWeekId, requestedExamWeekType }) => {
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
                    const normalize = (value) => String(value || '').replace(/\\s+/g, '');
                    const matchExamWeekType = (weekObj, type) => {
                      if (!type) {
                        return true;
                      }
                      const name = normalize(weekObj?.examWeekName || weekObj?.weekName || '');
                      if (type === '缓补考') {
                        return name.includes('缓补考');
                      }
                      if (type === '10-17周结课考') {
                        return name.includes('10-17周结课考') || (name.includes('10-17周') && name.includes('结课'));
                      }
                      if (type === '18-19周期末考') {
                        return name.includes('18-19周期末考') || (name.includes('18-19周') && name.includes('期末'));
                      }
                      return false;
                    };

                    let targetWeeks = requestedExamWeekId
                      ? examWeeks.filter((week) => week.examWeekId === requestedExamWeekId)
                      : examWeeks;
                    targetWeeks = targetWeeks.filter((week) => matchExamWeekType(week, requestedExamWeekType));

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
                      attempts,
                      targetWeekCount: targetWeeks.length,
                    };
                }""",
                {
                    "baseUrl": settings.base_url,
                    "requestedTerm": term,
                    "requestedExamWeekId": exam_week_id,
                    "requestedExamWeekType": exam_week_type,
                },
            )
            browser.close()

        exam_weeks = [self._build_exam_week(item) for item in payload.get("examWeeks", [])]
        if exam_week_id and not payload.get("attempts"):
            raise InvalidQueryError(f"Exam week {exam_week_id} was not found for term {payload['academicYear']}.")
        if exam_week_type and not payload.get("targetWeekCount"):
            raise InvalidQueryError(f"Exam week type {exam_week_type} was not found for term {payload['academicYear']}.")

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

                    const checkStuStatus = await doFetch(`${baseUrl}/achievement-manage/score-check/checkStuStatus?_t=${Date.now()}`);
                    const pullResponse = await doFetch(`${baseUrl}/achievement-manage/score-check/getPull?_t=${Date.now()}`);
                    const pie = await doFetch(`${baseUrl}/achievement-manage/score-check/getPicPie?_t=${Date.now()}`);
                    const pullJson = JSON.parse(pullResponse.text);
                    const pullData = pullJson.data || {};
                    const addScoreJson = JSON.parse(checkStuStatus.text);
                    const addScoreFlag = !!(addScoreJson.data && addScoreJson.data.addScoreFlag);

                    let scoSchoolYear;
                    let scoSemester;
                    if (requestedTerm === 'current') {
                      scoSchoolYear = pullData.selectYearPull?.[0]?.dataNumber;
                      scoSemester = pullData.selectTermPull?.[0]?.termNumber;
                    } else {
                      const parts = String(requestedTerm).split('-');
                      const startYear = Number(parts[0]);
                      const semester = parts[1];
                      if (Number.isFinite(startYear) && semester) {
                        scoSchoolYear = `${startYear}-${startYear + 1}`;
                        scoSemester = semester;
                      }
                    }
                    const trainTypeCode = pullData.selectTrainType?.[0]?.dataNumber || '01';
                    const normalizedTerm = scoSchoolYear && scoSemester
                      ? `${String(scoSchoolYear).split('-')[0]}-${String(scoSemester)}`
                      : requestedTerm;

                    const query = new URLSearchParams({
                      scoSchoolYear: String(scoSchoolYear || ''),
                      trainTypeCode: String(trainTypeCode),
                      addScoreFlag: String(addScoreFlag),
                      scoSemester: String(scoSemester || ''),
                      _t: String(Date.now()),
                    }).toString();
                    const list = await doFetch(`${baseUrl}/achievement-manage/score-check/list?${query}`);
                    const sortByYear = await doFetch(`${baseUrl}/achievement-manage/score-check/getSortByYear?${query}`);
                    const stuCreditSitlist = await doFetch(`${baseUrl}/achievement-manage/score-check/stuCreditSitlist?_t=${Date.now()}`);

                    return {
                      requestedTermResolved: `${scoSchoolYear || ''}-${scoSemester || ''}`,
                      normalizedTerm,
                      list,
                      sortByYear,
                      stuCreditSitlist,
                      pie,
                      pullResponse,
                      checkStuStatus,
                    };
                }""",
                {"baseUrl": settings.base_url, "requestedTerm": term},
            )
            browser.close()

        if payload["list"]["status"] != 200:
            raise UpstreamNotImplementedError(
                f"Grades endpoint returned unexpected status {payload['list']['status']}."
            )
        if payload["sortByYear"]["status"] != 200:
            raise UpstreamNotImplementedError(
                "Grades rank summary endpoint returned unexpected status "
                f"{payload['sortByYear']['status']}."
            )
        if payload["stuCreditSitlist"]["status"] != 200:
            raise UpstreamNotImplementedError(
                "Grades credit summary endpoint returned unexpected status "
                f"{payload['stuCreditSitlist']['status']}."
            )
        if payload["pie"]["status"] != 200:
            raise UpstreamNotImplementedError(
                f"Grades distribution endpoint returned unexpected status {payload['pie']['status']}."
            )

        list_json = json.loads(payload["list"]["text"])
        sort_json = json.loads(payload["sortByYear"]["text"])
        credit_json = json.loads(payload["stuCreditSitlist"]["text"])
        pie_json = json.loads(payload["pie"]["text"])

        rows = list_json.get("data", [])
        if not isinstance(rows, list):
            rows = []

        entries = self._parse_grade_entries(
            term=term if term != "current" else payload.get("normalizedTerm", term),
            rows=rows,
            include_raw=include_raw,
        )

        summary: dict = {}
        rank_summary = sort_json.get("data", {})
        if isinstance(rank_summary, dict):
            summary.update(rank_summary)
        credit_rows = credit_json.get("data", [])
        if isinstance(credit_rows, list) and credit_rows:
            first_row = credit_rows[0]
            if isinstance(first_row, dict):
                summary["credit_overview"] = first_row

        distribution_source = pie_json.get("data", [])
        if isinstance(distribution_source, dict):
            distribution = distribution_source.get("selectPie", [])
        else:
            distribution = distribution_source
        if not isinstance(distribution, list):
            distribution = []

        return GradesResponse(
            term=term if term != "current" else payload.get("normalizedTerm", term),
            stale=False,
            source="live",
            entries=entries,
            summary=summary,
            distribution=distribution,
            raw_records=rows if include_raw else None,
        )

    def _fetch_live_empty_classrooms(
        self,
        *,
        date_value: str,
        campus: str,
        section_range: str,
        section_start: int,
        section_end: int,
        include_raw: bool,
    ) -> EmptyClassroomsResponse:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(self._browser_manager.storage_state_path)
            )
            page = context.new_page()
            page.goto(
                f"{settings.base_url}/mk/schedule-web/#/classroomCheckStu?code=jwxsd_jsskqkjkxjscx",
                wait_until="networkidle",
                timeout=30000,
            )

            payload = page.evaluate(
                """async ({ baseUrl, requestedDate, requestedCampus }) => {
                    const mkHeaders = (jsonBody = false) => {
                      const headers = {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json, text/plain, */*',
                        'moduleid': 'null',
                        'menuid': 'jwxsd_jsskqkjkxjscx',
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
                    const normalize = (value) => String(value || '').replace(/\\s+/g, '').toLowerCase();

                    const campusResponse = await doFetch(
                      `${baseUrl}/base-info/campus/findCampusNamesBox?_t=${Date.now()}`,
                      { headers: mkHeaders() }
                    );
                    const campusJson = JSON.parse(campusResponse.text);
                    const campuses = Array.isArray(campusJson.data) ? campusJson.data : [];
                    const targetInput = normalize(requestedCampus);
                    const selectedCampus = campuses.find((item) => {
                      return normalize(item?.id) === targetInput
                        || normalize(item?.campusName) === targetInput
                        || normalize(item?.campusNumber) === targetInput;
                    }) || null;

                    let result = null;
                    if (selectedCampus) {
                      const body = {
                        pageNo: 1,
                        pageSize: 10,
                        total: true,
                        param: {
                          campusId: selectedCampus.id,
                          dateA: requestedDate,
                          dateB: requestedDate,
                          weekOrTime: 'time'
                        }
                      };
                      result = await doFetch(
                        `${baseUrl}/schedule/agg/classroomOccupy/pageCheckList?_t=${Date.now()}`,
                        {
                          method: 'POST',
                          headers: mkHeaders(true),
                          body: JSON.stringify(body)
                        }
                      );
                    }

                    return {
                      requestedDate,
                      requestedCampus,
                      selectedCampus,
                      campusResponse,
                      result
                    };
                }""",
                {
                    "baseUrl": settings.base_url,
                    "requestedDate": date_value,
                    "requestedCampus": campus,
                },
            )
            browser.close()

        if payload["campusResponse"]["status"] != 200:
            raise UpstreamNotImplementedError(
                "Campus lookup endpoint returned unexpected status "
                f"{payload['campusResponse']['status']}."
            )

        selected_campus = payload.get("selectedCampus")
        if not selected_campus:
            raise InvalidQueryError(f"Campus {campus} was not found.")

        result = payload.get("result")
        if not result or result["status"] != 200:
            status_value = result["status"] if result else "unknown"
            raise UpstreamNotImplementedError(
                f"Empty classroom endpoint returned unexpected status {status_value}."
            )

        result_json = json.loads(result["text"])
        result_data = result_json.get("data", {})
        rows = result_data.get("data", []) if isinstance(result_data, dict) else []
        if not isinstance(rows, list):
            rows = []

        entries = self._parse_empty_classroom_entries(
            date_value=date_value,
            campus_name=str(selected_campus.get("campusName") or ""),
            section_start=section_start,
            section_end=section_end,
            rows=rows,
            include_raw=include_raw,
        )

        return EmptyClassroomsResponse(
            date=date_value,
            campus=selected_campus.get("campusName") or campus,
            campus_id=str(selected_campus.get("id") or ""),
            section_range=section_range,
            stale=False,
            source="live",
            entries=entries,
            raw_records=rows if include_raw else None,
        )

    def _fetch_live_cet_scores(self, *, level: int, include_raw: bool) -> CetScoresResponse:
        with sync_playwright() as playwright:
            browser = playwright.chromium.launch(headless=True)
            context = browser.new_context(
                storage_state=str(self._browser_manager.storage_state_path)
            )
            page = context.new_page()
            page.goto(
                f"{settings.base_url}/mk/#/stuEnglishGradeAchievement?code=jwxsd_sljcjcx",
                wait_until="networkidle",
                timeout=30000,
            )

            payload = page.evaluate(
                """async ({ baseUrl }) => {
                    const mkHeaders = (jsonBody = false) => {
                      const headers = {
                        'X-Requested-With': 'XMLHttpRequest',
                        'Accept': 'application/json, text/plain, */*',
                        'moduleid': 'null',
                        'menuid': 'jwxsd_sljcjcx',
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

                    const body = {
                      pageNo: 1,
                      pageSize: 200,
                      total: true,
                      param: {}
                    };
                    const response = await doFetch(
                      `${baseUrl}/achievement-manage/englishGradeAchievement/stuPageList?_t=${Date.now()}`,
                      {
                        method: 'POST',
                        headers: mkHeaders(true),
                        body: JSON.stringify(body)
                      }
                    );

                    return {
                      response
                    };
                }""",
                {"baseUrl": settings.base_url},
            )
            browser.close()

        response = payload["response"]
        if response["status"] != 200:
            raise UpstreamNotImplementedError(
                f"CET endpoint returned unexpected status {response['status']}."
            )

        response_json = json.loads(response["text"])
        rows = self._extract_page_rows(response_json)
        matched_rows = [row for row in rows if self._detect_cet_level(row) == level]
        entries = [
            CetScoreEntry(
                level=self._first_non_empty(row, ["languageLevel", "cetLevel", "level", "examLevel"]),
                score=self._as_int(self._first_non_empty(row, ["writtenExaminationTotalScore", "totalScore", "score"])),
                exam_year=self._first_non_empty(row, ["examYear", "year"]),
                half_year=self._first_non_empty(
                    row,
                    ["thePastOrNextHalfYearName", "thePastOrNextHalfYear", "halfYear", "termHalf"],
                ),
                subject=self._first_non_empty(row, ["writtenExaminationSubject", "subject", "examSubject"]),
                exam_time=self._first_non_empty(row, ["writtenExaminationTime", "examTime", "time"]),
                written_exam_number=self._first_non_empty(
                    row, ["writtenExaminationNumber", "examNumber", "ticketNumber"]
                ),
                apply_campus=self._first_non_empty(
                    row, ["writtenExaminationApplyCampus", "applyCampus", "campus"]
                ),
                missing_test=self._as_bool_cn(
                    self._first_non_empty(row, ["whetherMissingTest", "missingTest"])
                ),
                violation=self._as_bool_cn(self._first_non_empty(row, ["whetherViolation", "violation"])),
                hearing_score=self._as_int(self._first_non_empty(row, ["hearingScore", "listeningScore"])),
                reading_score=self._as_int(self._first_non_empty(row, ["readingScore"])),
                writing_score=self._as_int(self._first_non_empty(row, ["writingScore"])),
                oral_score=self._first_non_empty(row, ["oralExamAchievement", "oralScore"]),
                raw_source=row if include_raw else None,
            )
            for row in matched_rows
        ]

        return CetScoresResponse(
            level=4 if level == 4 else 6,
            stale=False,
            source="live",
            total_records=len(rows),
            matched_records=len(matched_rows),
            entries=entries,
        )

    def _parse_empty_classroom_entries(
        self,
        *,
        date_value: str,
        campus_name: str,
        section_start: int,
        section_end: int,
        rows: list[dict],
        include_raw: bool,
    ) -> list[EmptyClassroomEntry]:
        entries: list[EmptyClassroomEntry] = []
        normalized_campus = campus_name.strip()

        for row in rows:
            if not isinstance(row, dict):
                continue
            row_campus = str(row.get("campus") or "").strip()
            if normalized_campus and row_campus and row_campus != normalized_campus:
                continue

            available_sections: list[int] = []
            for section_index, field_name in SECTION_FIELDS:
                cell = row.get(field_name)
                if not isinstance(cell, dict):
                    available_sections.append(section_index)
                    continue
                occupy_reason = cell.get("occupyReason")
                occupy_pro = cell.get("occupyPro")
                if occupy_reason in {None, ""} and occupy_pro in {None, ""}:
                    available_sections.append(section_index)

            if not available_sections:
                continue
            required_sections = set(range(section_start, section_end + 1))
            if not required_sections.issubset(set(available_sections)):
                continue

            available_periods = self._compress_sections(available_sections)
            entries.append(
                EmptyClassroomEntry(
                    date=str(row.get("date") or date_value),
                    campus=str(row.get("campus") or ""),
                    building=row.get("teachingBuild"),
                    classroom_name=str(row.get("classroomNum") or "").strip(),
                    classroom_id=str(row.get("classroomID") or "") or None,
                    available_sections=[str(item) for item in available_sections],
                    available_periods=available_periods,
                    raw_source=row if include_raw else None,
                )
            )

        return sorted(
            entries,
            key=lambda entry: (
                entry.building or "",
                entry.classroom_name,
            ),
        )

    def _compress_sections(self, sections: list[int]) -> list[str]:
        if not sections:
            return []
        ordered = sorted(set(sections))
        ranges: list[str] = []
        start = ordered[0]
        end = ordered[0]
        for section in ordered[1:]:
            if section == end + 1:
                end = section
                continue
            ranges.append(f"{start}-{end}节" if start != end else f"{start}节")
            start = section
            end = section
        ranges.append(f"{start}-{end}节" if start != end else f"{start}节")
        return ranges

    def _parse_section_range(self, section_range: str) -> tuple[int, int]:
        value = str(section_range or "").strip()
        match = re.fullmatch(r"(1[0-6]|[1-9])-(1[0-6]|[1-9])", value)
        if not match:
            raise InvalidQueryError(
                f"section_range must use X-Y within 1-16, received {section_range}."
            )
        start = int(match.group(1))
        end = int(match.group(2))
        if start > end:
            raise InvalidQueryError(
                f"section_range start must be <= end, received {section_range}."
            )
        return start, end

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
                        ["scoCourseName", "courseName", "course_name", "kcName", "kcmc"],
                    ),
                    course_code=self._first_non_empty(
                        row,
                        ["scoCourseNumber", "courseNo", "courseCode", "kch"],
                    ),
                    course_type=self._first_non_empty(
                        row,
                        [
                            "scoCourseCategoryName",
                            "scoCourseType",
                            "scoCourseTypeName",
                            "scoCourseNature",
                            "scoCourseNatureName",
                            "courseAttributeName",
                            "courseType",
                            "courseTypeName",
                            "kclb",
                        ],
                    ),
                    credit=self._as_float(
                        self._first_non_empty(
                            row,
                            ["scoCredit", "credit", "courseCredit", "xf"],
                        )
                    ),
                    score=self._first_non_empty(
                        row,
                        ["scoFinalScore", "score", "scoreValue", "achievement", "cj"],
                    ),
                    grade_point=self._as_float(
                        self._first_non_empty(
                            row,
                            ["scoPoint", "gradePoint", "grade_point", "point", "jd"],
                        )
                    ),
                    rank=self._first_non_empty(
                        row,
                        ["teachClassRank", "scoRank", "rank", "ranking", "pm"],
                    ),
                    exam_nature=self._first_non_empty(
                        row,
                        ["examNature", "examType", "ksxz", "scoExamNature", "scoExamNatureName"],
                    ),
                    assessment_method=self._first_non_empty(
                        row,
                        ["assessmentMethod", "assessmentType", "khfs", "scoAssessType", "scoAssessTypeName"],
                    ),
                    score_flag=self._first_non_empty(
                        row,
                        ["scoreFlag", "scoreSign", "cjbz", "scoScoreFlag", "scoScoreSign"],
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
            week=timetable.week,
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

    def _to_agent_empty_classrooms(
        self,
        classrooms: EmptyClassroomsResponse,
        *,
        include_raw: bool,
    ) -> EmptyClassroomsResponse:
        if include_raw:
            return classrooms

        entries = []
        for entry in classrooms.entries:
            cleaned = entry.model_copy(deep=True)
            cleaned.raw_source = None
            entries.append(cleaned)

        return EmptyClassroomsResponse(
            date=classrooms.date,
            campus=classrooms.campus,
            campus_id=classrooms.campus_id,
            section_range=classrooms.section_range,
            stale=classrooms.stale,
            source=classrooms.source,
            entries=entries,
            raw_records=None,
        )

    def _extract_page_rows(self, payload: dict) -> list[dict]:
        data = payload.get("data")
        if isinstance(data, list):
            return [item for item in data if isinstance(item, dict)]
        if isinstance(data, dict):
            rows = data.get("rows")
            if isinstance(rows, list):
                return [item for item in rows if isinstance(item, dict)]
            nested = data.get("data")
            if isinstance(nested, list):
                return [item for item in nested if isinstance(item, dict)]
        return []

    def _detect_cet_level(self, row: dict) -> int | None:
        if not isinstance(row, dict):
            return None

        def parse_level(text: str) -> int | None:
            normalized = text.lower().replace(" ", "")
            if any(token in normalized for token in ("cet-6", "cet6", "六级", "6级", "六")):
                return 6
            if any(token in normalized for token in ("cet-4", "cet4", "四级", "4级", "四")):
                return 4
            if normalized in {"6", "4"}:
                return int(normalized)
            return None

        preferred_keys = [
            "ksdj",
            "dengji",
            "level",
            "gradeLevel",
            "examLevel",
            "cetLevel",
            "testLevel",
            "gradeType",
            "examType",
            "kslx",
            "subjectName",
            "examName",
            "gradeName",
            "projectName",
            "kmmc",
        ]

        for key in preferred_keys:
            for row_key, row_value in row.items():
                if row_key == key or row_key.lower() == key.lower():
                    if row_value not in {None, ""}:
                        level = parse_level(str(row_value))
                        if level is not None:
                            return level

        for row_key, row_value in row.items():
            if row_value in {None, ""}:
                continue
            lower_key = row_key.lower()
            if any(token in lower_key for token in ("level", "grade", "type", "name", "cet", "dj", "ks")):
                level = parse_level(str(row_value))
                if level is not None:
                    return level
        return None

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

    def _as_int(self, value: str | None) -> int | None:
        if value in {None, ""}:
            return None
        try:
            return int(float(value))
        except (TypeError, ValueError):
            return None

    def _as_bool_cn(self, value: str | None) -> bool | None:
        if value in {None, ""}:
            return None
        normalized = str(value).strip().lower()
        if normalized in {"是", "yes", "true", "1"}:
            return True
        if normalized in {"否", "no", "false", "0"}:
            return False
        return None
