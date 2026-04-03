from dataclasses import dataclass
from pathlib import Path


@dataclass(slots=True)
class BrowserLaunchSpec:
    headless: bool
    channel: str | None
    storage_state_path: Path


class BrowserSessionManager:
    """Placeholder for the Playwright-backed browser lifecycle."""

    def __init__(self, spec: BrowserLaunchSpec) -> None:
        self._spec = spec

    @property
    def storage_state_path(self) -> Path:
        return self._spec.storage_state_path

    @property
    def headless(self) -> bool:
        return self._spec.headless

    @property
    def channel(self) -> str | None:
        return self._spec.channel

    def describe_login_strategy(self) -> str:
        return (
            "Launch a Chromium session with Playwright, navigate through SYSU NetID/CAS, "
            "persist storage state, and support manual takeover when automation stops."
        )
