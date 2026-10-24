"""Approval gate: an outreach batch is sendable only after BOTH Marketing and BD approve.

Any edit to the drafts resets approvals, so nobody approves text they haven't seen.
"""
from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone

from conferenceos.config import STATE_DIR

REQUIRED = ("marketing", "bd")
STATE_FILE = STATE_DIR / "approvals.json"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(drafts: list[dict]) -> str:
    return hashlib.sha256(json.dumps(drafts, sort_keys=True).encode()).hexdigest()[:12]


def _load() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def _save(state: dict) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    STATE_FILE.write_text(json.dumps(state, indent=2))


def submit(batch_id: str, event_id: str, drafts: list[dict]) -> dict:
    state = _load()
    state[batch_id] = {"event_id": event_id, "drafts": drafts, "digest": _digest(drafts),
                       "approvals": {}, "status": "pending", "sent_at": None, "created_at": _now()}
    _save(state)
    return state[batch_id]


def get(batch_id: str) -> dict | None:
    return _load().get(batch_id)


def update_drafts(batch_id: str, drafts: list[dict]) -> dict:
    state = _load()
    b = state[batch_id]
    if b["status"] == "sent":
        raise ValueError("batch already sent")
    if _digest(drafts) != b["digest"]:
        b.update(drafts=drafts, digest=_digest(drafts), approvals={}, status="pending")
    _save(state)
    return b


def approve(batch_id: str, role: str, approver: str) -> dict:
    if role not in REQUIRED:
        raise ValueError(f"unknown role {role}")
    state = _load()
    b = state[batch_id]
    if b["status"] == "sent":
        raise ValueError("batch already sent")
    b["approvals"][role] = {"by": approver, "at": _now(), "digest": b["digest"]}
    b["status"] = "approved" if is_sendable(b) else "pending"
    _save(state)
    return b


def is_sendable(b: dict) -> bool:
    return all(b["approvals"].get(r, {}).get("digest") == b["digest"] for r in REQUIRED)


def mark_sent(batch_id: str) -> dict:
    """Demo 'send': records the send; no emails leave the system."""
    state = _load()
    b = state[batch_id]
    if not is_sendable(b):
        raise PermissionError("needs Marketing AND BD approval on the current drafts")
    b.update(status="sent", sent_at=_now())
    _save(state)
    return b
