import json
from pathlib import Path

from sysu_jwxt_agent.schemas import TimetableEntry, TimetableResponse


class TimetableCache:
    def __init__(self, cache_dir: Path) -> None:
        self._cache_dir = cache_dir
        self._cache_dir.mkdir(parents=True, exist_ok=True)

    def _cache_path(self, term: str) -> Path:
        return self._cache_dir / f"{term}.json"

    def load(self, term: str) -> TimetableResponse | None:
        path = self._cache_path(term)
        if not path.exists():
            return None

        payload = json.loads(path.read_text(encoding="utf-8"))
        entries = [TimetableEntry.model_validate(item) for item in payload["entries"]]
        return TimetableResponse(
            term=payload["term"],
            stale=True,
            source="cache",
            entries=entries,
        )

    def save(self, timetable: TimetableResponse) -> None:
        path = self._cache_path(timetable.term)
        path.write_text(
            timetable.model_dump_json(indent=2),
            encoding="utf-8",
        )

