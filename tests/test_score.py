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


def event(eid, start, region, pass_, booth, travel, sponsors=(), prior=(), speakers=(), exhibitors=()):
    return {
        "event_id": eid, "series": eid, "name": s(eid), "edition_year": 2027,
        "start_date": s(start), "end_date": s(start), "city": s("X"), "country": s("US"),
        "region": region, "url": "https://example.test", "topics": ["lab informatics"],
        "costs": {"pass_price_usd": s(pass_), "booth_price_usd": s(booth, "estimated"),
                  "travel_est_usd": s(travel, "estimated")},
        "sponsors": [{"name": n, "tier": "gold", "prov": "scraped"} for n in sponsors]
        + [{"name": n, "tier": "exhibitor", "prov": "scraped"} for n in exhibitors],
        "exhibitors_prior_year": [{"name": n, "prov": "estimated", "basis": "prior_year_exhibitor"} for n in prior],
        "speakers": [{"name": p, "title": "VP", "company": c, "prov": "scraped"} for p, c in speakers],
    }


DOC = {"events": [
    # 3 accounts (one via alias "Genentech" -> Roche, one via speaker) for $20k -> 1.5 per $10k
    event("cheap-dense", "2027-03-01", "US", 5000, 10000, 5000,
          sponsors=["Moderna, Inc.", "Some Vendor"], prior=["Genentech"], speakers=[("Jane Doe", "Novartis AG")]),
    # 2 accounts, duplicate presence for Moderna counted once, $40k -> 0.5 per $10k
    event("pricey", "2027-05-01", "EU", 10000, 20000, 10000,
          sponsors=["Moderna"], exhibitors=["Bayer"], prior=["Moderna"]),
    # out of window
    event("too-late", "2027-09-01", "US", 1, 1, 1, sponsors=["Moderna"]),
]}


MASKED = [  # masked attendee list rows (company + title only)
    {"series": "pricey", "year": "2026", "company": "MODERNA THERAPEUTICS", "title": "Scientist", "simulated": "true"},
    {"series": "pricey", "year": "2026", "company": "Moderna, Inc.", "title": "Lab Manager", "simulated": "true"},
    {"series": "pricey", "year": "2026", "company": "Moderna", "title": "", "simulated": "true"},
    {"series": "pricey", "year": "2026", "company": "", "title": "CEO", "simulated": "true"},
    {"series": "not-in-cache", "year": "2026", "company": "Bayer", "title": "CSO", "simulated": "true"},
]


@pytest.fixture(scope="module")
def graph():
    g = get_db().select_graph("conferenceos_test")
    build(g, DOC, masked=MASKED)
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
    # exhibitors must not be explained as sponsors (Qodo PR #3)
    assert any(w.startswith("Bayer -[EXHIBITS_AT]->") for w in rows[1]["why"])


def test_masked_attendees_roll_up_per_account(graph):
    res = graph.query(
        """MATCH (a:Account)-[r:REGISTERED_AT]->(e:Event)
           RETURN a.name, e.event_id, r.count, r.titles, r.prov, r.year""")
    # three spellings of Moderna resolve to one account edge; blank company and unknown series are skipped
    assert res.result_set == [["Moderna", "pricey", 3, ["Lab Manager", "Scientist"], "simulated", 2026]]
    # reference data only: does not change the ranking
    assert [r["accounts_present"] for r in score_events(graph)] == [3, 2]
