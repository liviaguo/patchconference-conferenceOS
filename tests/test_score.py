"""Loads a tiny hand-built cache (test data only) into a throwaway graph and checks the ranking."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos.graph.client import get_db  # noqa: E402
from conferenceos.graph.load import build, company_key  # noqa: E402
from conferenceos.graph.score import score_events  # noqa: E402

T = "2026-10-24T00:00:00+00:00"


def s(v, prov="scraped"):
    return {"value": v, "prov": prov, "source_url": "https://example.test", "fetched_at": T, "note": ""}


def event(eid, start, region, pass_, booth, travel, sponsors=(), prior=(), speakers=()):
    return {
        "event_id": eid, "series": eid, "name": s(eid), "edition_year": 2027,
        "start_date": s(start), "end_date": s(start), "city": s("X"), "country": s("US"),
        "region": region, "url": "https://example.test", "topics": ["lab informatics"],
        "costs": {"pass_price_usd": s(pass_), "booth_price_usd": s(booth, "estimated"),
                  "travel_est_usd": s(travel, "estimated")},
        "sponsors": [{"name": n, "tier": "gold", "prov": "scraped"} for n in sponsors],
        "exhibitors_prior_year": [{"name": n, "prov": "estimated", "basis": "prior_year_exhibitor"} for n in prior],
        "speakers": [{"name": p, "title": "VP", "company": c, "prov": "scraped"} for p, c in speakers],
    }


DOC = {"events": [
    # 3 accounts (one via alias "Genentech" -> Roche, one via speaker) for $20k -> 1.5 per $10k
    event("cheap-dense", "2027-03-01", "US", 5000, 10000, 5000,
          sponsors=["Moderna, Inc.", "Some Vendor"], prior=["Genentech"], speakers=[("Jane Doe", "Novartis AG")]),
    # 2 accounts, duplicate presence for Moderna counted once, $40k -> 0.5 per $10k
    event("pricey", "2027-05-01", "EU", 10000, 20000, 10000,
          sponsors=["Moderna", "Bayer"], prior=["Moderna"]),
    # out of window
    event("too-late", "2027-09-01", "US", 1, 1, 1, sponsors=["Moderna"]),
]}


@pytest.fixture(scope="module")
def graph():
    g = get_db().select_graph("conferenceos_test")
    build(g, DOC)
    yield g
    g.delete()


def test_company_key_strips_suffixes():
    assert company_key("Moderna, Inc.") == company_key("Moderna") == "moderna"


def test_ranking_and_paths(graph):
    rows = score_events(graph)
    assert [r["event_id"] for r in rows] == ["cheap-dense", "pricey"]

    top = rows[0]
    assert top["accounts_present"] == 3
    assert top["cost"] == 20000
    assert top["reached_per_10k"] == pytest.approx(1.5)
    assert any("SPEAKS_AT" in w and "Jane Doe" in w for w in top["why"])
    assert any(w.startswith("Roche (as Genentech) -[ATTENDS]->") and "(estimated)" in w for w in top["why"])

    assert rows[1]["accounts_present"] == 2
    assert rows[1]["reached_per_10k"] == pytest.approx(0.5)
