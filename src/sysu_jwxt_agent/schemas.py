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
    raw_source: dict = Field(default_factory=dict)


class TimetableResponse(BaseModel):
    term: str
    stale: bool = False
    source: Literal["live", "cache"]
    entries: list[TimetableEntry]
