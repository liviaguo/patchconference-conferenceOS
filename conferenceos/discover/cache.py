from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from conferenceos.config import CACHE_DIR


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def write(events: list[dict], source: str = "brightdata") -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = CACHE_DIR / f"events_{ts}.json"
    path.write_text(json.dumps({"fetched_at": now_iso(), "source": source, "events": events}, indent=2))
    return path


def latest() -> dict | None:
    files = sorted(CACHE_DIR.glob("events_*.json"))
    return json.loads(files[-1].read_text()) if files else None
