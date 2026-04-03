from __future__ import annotations

import argparse
import json
from pathlib import Path

from sysu_jwxt_agent.schemas import ImportStateRequest
from sysu_jwxt_agent.services.auth import AuthService
from sysu_jwxt_agent.services.browser import BrowserLaunchSpec, BrowserSessionManager


ROOT = Path(__file__).resolve().parent.parent
STATE_DIR = ROOT / "data" / "state"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Import a browser-exported session into Playwright storage state."
    )
    parser.add_argument(
        "--input",
        required=True,
        help="Path to a JSON file containing either Playwright storageState or a cookie list.",
    )
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    input_path = Path(args.input)
    payload = json.loads(input_path.read_text(encoding="utf-8"))

    auth = AuthService(
        STATE_DIR,
        browser_manager=BrowserSessionManager(
            BrowserLaunchSpec(
                headless=True,
                channel=None,
                storage_state_path=STATE_DIR / "storage_state.json",
            )
        ),
    )

    if isinstance(payload, list):
        request = ImportStateRequest(cookies=payload)
    else:
        request = ImportStateRequest(storage_state=payload)

    result = auth.import_state(request)

    print(result.model_dump_json(indent=2))


if __name__ == "__main__":
    main()
