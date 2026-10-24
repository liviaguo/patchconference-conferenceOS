"""Regression cases taken from the real first scrape (flagged by Qodo on PR 4)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos.discover.validate import reject_reason  # noqa: E402

KEEP = [
    ("ASGCT Annual Meeting", "US", "2027 Annual Meeting", "US", "https://www.asgct.org/events-meetings/2027-annual-meeting"),
    ("Society of Toxicology Annual Meeting", "US", "SOT Annual Meeting and ToxExpo", "US", "https://www.toxicology.org/2027/"),
    ("BIO-Europe Spring", "EU", "BIO-Europe Spring 2027", "EU", "https://example.com/x"),
    ("SLAS International Conference", "US", "SLAS2027 International Conference & Exhibition", "US",
     "https://www.slas.org/events-calendar/slas2027-international-conference-exhibition/"),
]
REJECT = [
    ("SLAS Europe", "EU", "AI 2027", "EU", "https://ai-2027.com/"),
    ("CPHI Americas", "US", "CPHI", "OTHER", "https://www.cphi.com/"),
    ("Paperless Lab Academy", "EU", "Paperless Lab Academy", "OTHER", "https://zifo.com/event/paperless-lab-academy-india-2025/"),
]


def test_acronym_with_year_matches_without_url():
    assert reject_reason("SLAS Europe", "EU", "SLAS2027 Europe", "EU", "https://example.com/") is None


def test_rejects_wrong_edition_year():
    assert "2026 edition" in reject_reason("Pittcon", "US", "Pittcon 2026", "US", "https://pittcon.org", 2026)


@pytest.mark.parametrize("series,hint,name,region,url", KEEP)
def test_keeps_real_pages(series, hint, name, region, url):
    assert reject_reason(series, hint, name, region, url) is None


@pytest.mark.parametrize("series,hint,name,region,url", REJECT)
def test_rejects_wrong_pages(series, hint, name, region, url):
    assert reject_reason(series, hint, name, region, url) is not None
