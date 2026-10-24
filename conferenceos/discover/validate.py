"""Candidate-page validation: reject pages that aren't about the seeded event or its region.

Search's first useful result is sometimes an unrelated site (ai-2027.com for "SLAS Europe 2027")
or another regional edition (CPHI India for "CPHI Americas").
"""
from __future__ import annotations

import re

STOP = {"conference", "annual", "meeting", "international", "expo", "the", "of", "and", "summit",
        "exhibition", "europe", "americas", "spring", "convention", "society"}
US_EU = {"US", "EU"}


TARGET_YEAR = 2027


def _tokens(s: str) -> set[str]:
    words = re.findall(r"[a-z0-9-]+", (s or "").lower())
    # "SLAS2027" should match "SLAS": also index each word with a trailing year stripped
    return set(words) | {re.sub(r"-?(19|20)\d\d$", "", w) for w in words}


def same_event(series: str, page_name: str, url: str = "") -> bool:
    """The page's event name or URL shares a distinctive word with the series name.

    URL counts because official pages can have generic titles ("2027 Annual Meeting" on asgct.org).
    """
    want = {w for w in _tokens(series) if w not in STOP and not w.isdigit()}
    return bool(want & (_tokens(page_name) | _tokens(url.replace(".", " ").replace("/", " "))))


def reject_reason(series: str, region_hint: str, page_name: str | None, region: str, url: str = "",
                  edition_year: int | None = None) -> str | None:
    if not same_event(series, page_name or "", url):
        return f"page is about {page_name!r}, not {series!r}"
    if edition_year is not None and edition_year != TARGET_YEAR:
        return f"page is the {edition_year} edition, not {TARGET_YEAR}"
    if region_hint in US_EU and region not in US_EU:
        return f"page is a {region} edition; seed expects {region_hint}"
    return None
