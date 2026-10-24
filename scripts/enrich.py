"""Second pass: scrape each cached event's speakers + exhibitors/sponsors pages and merge into a new cache file.

Event homepages rarely list who's coming; dedicated pages do.
Usage: .venv/bin/python scripts/enrich.py
"""
from __future__ import annotations

import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos.discover import cache  # noqa: E402
from conferenceos.discover.validate import same_event  # noqa: E402
from discover import scrape_and_extract  # noqa: E402


def enrich(e: dict) -> dict:
    series, year = e["series"], str(e.get("edition_year") or 2027)
    seen_s = {s["name"].lower() for s in e["sponsors"]}
    seen_p = {p["name"].lower() for p in e["speakers"]}
    added_s = added_p = 0
    for query in (f"{series} {year} speakers", f"{series} {year} exhibitors sponsors"):
        try:
            info, url = scrape_and_extract(query, year)
        except Exception as ex:
            print(f"  ! {series} [{query}]: {type(ex).__name__}: {ex}")
            continue
        if not url:
            continue
        # Only trust lists from pages about this edition
        if info.get("edition_year") not in (None, int(year)):
            print(f"  - {series}: skipped {url} (edition {info.get('edition_year')})")
            continue
        # ...and that are about this event at all (guards against unrelated pages' sponsor lists)
        if not same_event(series, info.get("name") or "", url):
            print(f"  - {series}: skipped {url} (page is about {info.get('name')!r})")
            continue
        for s in (info.get("sponsors") or []) + [{"name": n, "tier": "exhibitor"} for n in info.get("exhibitors") or []]:
            if s.get("name") and s["name"].lower() not in seen_s:
                seen_s.add(s["name"].lower())
                # Record the year the page states (may be None), don't stamp the target year on it
                e["sponsors"].append({"name": s["name"], "tier": s.get("tier"), "prov": "scraped",
                                      "year": info.get("edition_year"), "source_url": url,
                                      "fetched_at": cache.now_iso()})
                added_s += 1
        for p in info.get("speakers") or []:
            if p.get("name") and p["name"].lower() not in seen_p:
                seen_p.add(p["name"].lower())
                e["speakers"].append(dict(p, prov="scraped", source_url=url, fetched_at=cache.now_iso()))
                added_p += 1
    print(f"  ✓ {series}: +{added_s} sponsors/exhibitors, +{added_p} speakers")
    return e


def main() -> None:
    doc = cache.latest()
    if not doc:
        sys.exit("no cache")
    with ThreadPoolExecutor(max_workers=6) as pool:
        events = list(pool.map(enrich, doc["events"]))
    print("Wrote", cache.write(events, source="brightdata+enrich"))


if __name__ == "__main__":
    main()
