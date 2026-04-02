from typing import Literal

from pydantic import BaseModel, Field


class HealthResponse(BaseModel):
    status: Literal["ok"]


class SessionStatus(BaseModel):
    authenticated: bool
    login_required: bool = False
    manual_step_required: bool = False
    message: str
    cas_login_url: str | None = None
    upstream_code: int | None = None


class CookieItem(BaseModel):
    name: str
    value: str
    domain: str
    path: str = "/"
    expires: int | float = -1
    httpOnly: bool = False
    secure: bool = True
    sameSite: Literal["Strict", "Lax", "None"] | None = None


class ImportStateRequest(BaseModel):
    cookies: list[CookieItem] | None = None
    origins: list[dict] | None = None
    storage_state: dict | None = None


class ImportStateResponse(BaseModel):
    imported: bool
    cookie_count: int
    state_path: str
    message: str


class TimetableEntry(BaseModel):
    term: str
    course_name: str
    teacher: str | None = None
    weekday: int = Field(ge=1, le=7)
    start_section: int = Field(ge=1)
    end_section: int = Field(ge=1)
    weeks: list[int] = Field(default_factory=list)
    location: str | None = None
    raw_source: dict | None = None


class TimetableResponse(BaseModel):
    term: str
    stale: bool = False
    source: Literal["live", "cache"]
    entries: list[TimetableEntry]


class ExamWeek(BaseModel):
    exam_week_id: str
    exam_week_name: str
    start_date: str | None = None
    end_date: str | None = None
    apply_range: str | None = None


class ExamEntry(BaseModel):
    term: str
    exam_week_id: str | None = None
    exam_week_name: str | None = None
    course_name: str | None = None
    exam_date: str | None = None
    exam_time: str | None = None
    duration_minutes: int | None = None
    location: str | None = None
    exam_stage: str | None = None
    exam_mode: str | None = None
    weekday: int | None = Field(default=None, ge=1, le=7)
    section_label: str | None = None
    raw_source: dict | None = None


class ExamsResponse(BaseModel):
    term: str
    stale: bool = False
    source: Literal["live", "cache"]
    selected_exam_week: ExamWeek | None = None
    exam_weeks: list[ExamWeek] = Field(default_factory=list)
    entries: list[ExamEntry] = Field(default_factory=list)
    raw_records: list[dict] | None = None


class GradeEntry(BaseModel):
    term: str
    course_name: str | None = None
    course_code: str | None = None
    course_type: str | None = None
    credit: float | None = None
    score: str | None = None
    grade_point: float | None = None
    exam_nature: str | None = None
    assessment_method: str | None = None
    score_flag: str | None = None
    raw_source: dict | None = None


class GradesResponse(BaseModel):
    term: str
    stale: bool = False
    source: Literal["live", "cache"]
    entries: list[GradeEntry] = Field(default_factory=list)
    summary: dict = Field(default_factory=dict)
    distribution: list[dict] = Field(default_factory=list)
    raw_records: list[dict] | None = None
