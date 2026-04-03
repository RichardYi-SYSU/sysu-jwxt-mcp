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


class KeepaliveStatus(BaseModel):
    enabled: bool
    interval_seconds: int
    jitter_seconds: int = 0
    running: bool
    authenticated: bool | None = None
    last_ok: bool | None = None
    last_checked_at: str | None = None
    last_error: str | None = None
    tick_count: int = 0
    consecutive_failures: int = 0


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


class QrLoginStartResponse(BaseModel):
    login_session_id: str
    status: Literal["pending", "scanned", "confirmed", "success", "expired", "failed"]
    qr_image_base64: str | None = None
    qr_ascii: str | None = None
    qr_page_url: str | None = None
    qr_png_path: str | None = None
    expires_at: str | None = None
    message: str


class QrLoginStatusResponse(BaseModel):
    login_session_id: str
    status: Literal["pending", "scanned", "confirmed", "success", "expired", "failed"]
    authenticated: bool
    expires_at: str | None = None
    last_error: str | None = None
    state_persisted: bool = False
    state_path: str | None = None
    cookie_count: int = 0
    qr_png_path: str | None = None
    trace_path: str | None = None
    message: str | None = None


class QrLoginConfirmResponse(BaseModel):
    login_session_id: str
    status: Literal["success"]
    authenticated: bool
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
    week: int | None = None
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
    rank: str | None = None
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


class EmptyClassroomEntry(BaseModel):
    date: str
    campus: str
    building: str | None = None
    classroom_name: str
    classroom_id: str | None = None
    available_sections: list[str] = Field(default_factory=list)
    available_periods: list[str] = Field(default_factory=list)
    raw_source: dict | None = None


class EmptyClassroomsResponse(BaseModel):
    date: str
    campus: str
    campus_id: str
    section_range: str
    stale: bool = False
    source: Literal["live", "cache"]
    entries: list[EmptyClassroomEntry] = Field(default_factory=list)
    raw_records: list[dict] | None = None


class CetScoreEntry(BaseModel):
    level: str | None = None
    score: int | None = None
    exam_year: str | None = None
    half_year: str | None = None
    subject: str | None = None
    exam_time: str | None = None
    written_exam_number: str | None = None
    apply_campus: str | None = None
    missing_test: bool | None = None
    violation: bool | None = None
    hearing_score: int | None = None
    reading_score: int | None = None
    writing_score: int | None = None
    oral_score: str | None = None
    raw_source: dict | None = None


class CetScoresResponse(BaseModel):
    level: Literal[4, 6]
    stale: bool = False
    source: Literal["live", "cache"]
    total_records: int = 0
    matched_records: int = 0
    entries: list[CetScoreEntry] = Field(default_factory=list)
