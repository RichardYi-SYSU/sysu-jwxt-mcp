import json
from pathlib import Path

from sysu_jwxt_agent.schemas import TimetableEntry, TimetableResponse


class TimetableCache:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, term: str, week: int | None) -> Path:
        week_token = f"w{week}" if week is not None else "wcurrent"
        return self._cache_dir / f"{term}__{week_token}.json"

    def load(self, term: str, week: int | None) -> TimetableResponse | None:
        path = self._cache_path(term, week)
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = [TimetableEntry.model_validate(item) for item in payload["entries"]]
        return TimetableResponse(
            term=payload["term"],
            week=payload.get("week"),
            stale=True,
            source="cache",
            entries=entries,
        )

    def save(self, timetable: TimetableResponse) -> None:
        path = self._cache_path(timetable.term, timetable.week)
        path.write_text(
            timetable.model_dump_json(indent=2),
            encoding="utf-8",
        )
