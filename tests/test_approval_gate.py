import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos.approvals import gate  # noqa: E402


@pytest.fixture(autouse=True)
def tmp_state(tmp_path, monkeypatch):
    monkeypatch.setattr(gate, "STATE_DIR", tmp_path)
    monkeypatch.setattr(gate, "STATE_FILE", tmp_path / "approvals.json")


DRAFTS = [{"account": "Moderna", "subject": "Hi", "body": "Meet at SLAS?"}]


def test_needs_both_roles():
    gate.submit("b1", "e1", DRAFTS)
    gate.approve("b1", "marketing", "m@x")
    with pytest.raises(PermissionError):
        gate.mark_sent("b1")
    gate.approve("b1", "bd", "b@x")
    assert gate.mark_sent("b1")["status"] == "sent"


def test_edit_resets_approvals():
    gate.submit("b2", "e1", DRAFTS)
    gate.approve("b2", "marketing", "m@x")
    gate.approve("b2", "bd", "b@x")
    gate.update_drafts("b2", [dict(DRAFTS[0], body="changed")])
    assert not gate.is_sendable(gate.get("b2"))
    with pytest.raises(PermissionError):
        gate.mark_sent("b2")


def test_unknown_role_rejected():
    gate.submit("b3", "e1", DRAFTS)
    with pytest.raises(ValueError):
        gate.approve("b3", "finance", "f@x")
