"""Approval gate: an outreach batch is sendable only after BOTH Marketing and BD approve.

Any edit to the drafts resets approvals, so nobody approves text they haven't seen.
Marketing and BD must be different people.

Demo scope (auth was cut): approver identity is self-declared and state is a local JSON file,
locked only within this process. A real deployment needs SSO-verified roles and a
transactional store.
"""
from __future__ import annotations

import hashlib
import json
import os
import threading
from datetime import datetime, timezone

from conferenceos.config import STATE_DIR

REQUIRED = ("marketing", "bd")
STATE_FILE = STATE_DIR / "approvals.json"
_LOCK = threading.Lock()  # serializes read-modify-write across Streamlit sessions in one process


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


def _digest(drafts: list[dict]) -> str:
    return hashlib.sha256(json.dumps(drafts, sort_keys=True).encode()).hexdigest()[:12]


def _load() -> dict:
    return json.loads(STATE_FILE.read_text()) if STATE_FILE.exists() else {}


def _save(state: dict) -> None:
    # write-then-rename so a crash never leaves a half-written approvals file
    STATE_FILE.parent.mkdir(parents=True, exist_ok=True)
    tmp = STATE_FILE.with_suffix(".tmp")
    tmp.write_text(json.dumps(state, indent=2))
    os.replace(tmp, STATE_FILE)


def _open_batch(state: dict, batch_id: str) -> dict:
    b = state[batch_id]
    if b["status"] == "sent":
        raise ValueError("batch already sent")
    return b


def get(batch_id: str) -> dict | None:
    return _load().get(batch_id)


def submit(batch_id: str, event_id: str, drafts: list[dict]) -> dict:
    with _LOCK:
        state = _load()
        if state.get(batch_id, {}).get("status") == "sent":
            raise ValueError("batch already sent; it can't be replaced")
        state[batch_id] = {"event_id": event_id, "drafts": drafts, "digest": _digest(drafts),
                           "approvals": {}, "status": "pending", "sent_at": None, "created_at": _now()}
        _save(state)
        return state[batch_id]


def update_drafts(batch_id: str, drafts: list[dict]) -> dict:
    with _LOCK:
        state = _load()
        b = _open_batch(state, batch_id)
        if _digest(drafts) != b["digest"]:
            b.update(drafts=drafts, digest=_digest(drafts), approvals={}, status="pending")
        _save(state)
        return b


def approve(batch_id: str, role: str, approver: str, digest: str | None = None) -> dict:
    """`digest` is the version the approver was looking at; a stale view can't approve newer text."""
    if role not in REQUIRED:
        raise ValueError(f"unknown role {role}")
    approver = (approver or "").strip()
    if not approver:
        raise ValueError("approver name required")
    with _LOCK:
        state = _load()
        b = _open_batch(state, batch_id)
        if digest is not None and digest != b["digest"]:
            raise ValueError("drafts changed since you loaded them; review again")
        for other, a in b["approvals"].items():
            if other != role and a["by"].lower() == approver.lower() and a["digest"] == b["digest"]:
                raise PermissionError("Marketing and BD approvals must come from different people")
        b["approvals"][role] = {"by": approver, "at": _now(), "digest": b["digest"]}
        b["status"] = "approved" if is_sendable(b) else "pending"
        _save(state)
        return b


def is_sendable(b: dict) -> bool:
    return b["status"] != "sent" and all(
        b["approvals"].get(r, {}).get("digest") == b["digest"] for r in REQUIRED)


def mark_sent(batch_id: str) -> dict:
    """Demo 'send': records the send once; no emails leave the system."""
    with _LOCK:
        state = _load()
        b = _open_batch(state, batch_id)
        if not is_sendable(b):
            raise PermissionError("needs Marketing AND BD approval on the current drafts")
        b.update(status="sent", sent_at=_now())
        _save(state)
        return b
