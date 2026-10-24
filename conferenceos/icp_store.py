"""The ICP the app is currently using: edited in the UI, else data/icp_accounts.csv."""
from __future__ import annotations

import json

from conferenceos.config import STATE_DIR
from conferenceos.graph.load import load_accounts

ICP_FILE = STATE_DIR / "icp.json"


def load() -> list[dict]:
    if ICP_FILE.exists():
        return json.loads(ICP_FILE.read_text())
    return [dict(a, tier=int(a["tier"])) for a in load_accounts()]


def save(accounts: list[dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    ICP_FILE.write_text(json.dumps(accounts, indent=2))
