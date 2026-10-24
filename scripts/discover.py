"""Discover events via Bright Data (SERP -> Unlocker -> LLM extract) and write data/cache/events_*.json.

Usage: .venv/bin/python scripts/discover.py [--limit N]
"""
from __future__ import annotations

import argparse
import csv
import re
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos.config import DATA  # noqa: E402
from conferenceos.discover import brightdata, cache  # noqa: E402
from conferenceos.discover.validate import reject_reason, same_event  # noqa: E402
from conferenceos.discover.extract import extract_event  # noqa: E402

EU_CODES = {
    "AT", "BE", "BG", "CH", "CY", "CZ", "DE", "DK", "EE", "ES", "FI", "FR", "GB", "UK", "GR", "HR",
    "HU", "IE", "IS", "IT", "LT", "LU", "LV", "MT", "NL", "NO", "PL", "PT", "RO", "SE", "SI", "SK",
}
# Fixed FX for the demo; converted values are flagged in `note`.
FX_TO_USD = {"USD": 1.0, "EUR": 1.08, "GBP": 1.27, "CHF": 1.13}
# Used only when the page doesn't publish a booth price.
BOOTH_DEFAULT_USD = {"US": 15000, "EU": 13000}
SKIP_DOMAINS = ("linkedin.com", "facebook.com", "x.com", "twitter.com", "wikipedia.org", "youtube.com", "eventbrite")


def sourced(value, prov: str, source_url: str | None, fetched_at: str, note: str = "") -> dict:
    return {"value": value, "prov": prov, "source_url": source_url, "fetched_at": fetched_at, "note": note}


def slug(s: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", s.lower()).strip("-")


def first_useful_link(results: list[dict], year: str = "2027") -> str | None:
    # Prefer pages about the target edition; search often ranks last year's page first.
    results = sorted(results, key=lambda r: year not in f"{r.get('title')} {r.get('link')}")
    for r in results:
        link = r.get("link") or ""
        if link and not any(d in link for d in SKIP_DOMAINS):
            return link
    return None


def scrape_and_extract(query: str, year: str = "2027") -> tuple[dict, str | None]:
    url = first_useful_link(brightdata.serp(query), year)
    if not url:
        return {}, None
    return extract_event(brightdata.unlock(url), url), url


def to_usd(price: dict | None) -> tuple[float | None, str]:
    if not price or price.get("amount") is None:
        return None, ""
    cur = (price.get("currency") or "USD").upper()
    rate = FX_TO_USD.get(cur)
    if rate is None:
        return None, f"unsupported currency {cur}"
    note = price.get("label") or ""
    if cur != "USD":
        note = f"{note}; {price['amount']} {cur} converted at {rate}".strip("; ")
    return round(price["amount"] * rate), note


def discover_one(seed: dict, travel: dict) -> dict | None:
    series = seed["series"]
    info, url = scrape_and_extract(seed["search_query"])
    if not url:
        print(f"  ! {series}: no result")
        return None
    t = cache.now_iso()

    cc = (info.get("country_code") or "").upper()
    region = "US" if cc == "US" else "EU" if cc in EU_CODES else (seed["region_hint"] if not cc else "OTHER")
    why_not = reject_reason(series, seed["region_hint"], info.get("name"), region, url, info.get("edition_year"))
    if why_not:
        print(f"  ! {series}: rejected {url}: {why_not}")
        return None

    sponsors = [dict(s, prov="scraped", year=info.get("edition_year"), source_url=url, fetched_at=t)
                for s in info.get("sponsors") or []]
    sponsors += [{"name": n, "tier": "exhibitor", "prov": "scraped", "year": info.get("edition_year"),
                  "source_url": url, "fetched_at": t} for n in info.get("exhibitors") or []]
    speakers = [dict(s, prov="scraped", source_url=url, fetched_at=t) for s in info.get("speakers") or []]

    # 2027 lists are often unpublished this far out; prior-year exhibitors are an estimate of attendance.
    # A failed history lookup shouldn't discard an event whose main page already extracted fine.
    try:
        prior, prior_url = scrape_and_extract(f"{series} 2026 exhibitor list", "2026")
    except Exception as ex:
        print(f"  - {series}: prior-year lookup failed ({type(ex).__name__}); continuing without it")
        prior, prior_url = {}, None
    if prior_url and (not same_event(series, prior.get("name") or "", prior_url)
                      or prior.get("edition_year") not in (None, 2026)):
        print(f"  - {series}: ignored prior-year list from {prior_url} (page is about {prior.get('name')!r})")
        prior = {}
    prior_exhibitors = [{"name": n, "prov": "estimated", "year": 2026, "source_url": prior_url,
                         "basis": "prior_year_exhibitor", "fetched_at": t}
                        for n in (prior.get("exhibitors") or []) + [s["name"] for s in prior.get("sponsors") or []]]

    pass_usd, pass_note = to_usd(info.get("pass_price"))
    booth_usd, booth_note = to_usd(info.get("booth_price"))
    tr = travel.get(region) or travel["US"]
    travel_usd = int(tr["per_person_usd"]) * int(tr["default_headcount"])
    headcount = int(tr["default_headcount"])

    costs = {
        "pass_price_usd": sourced(pass_usd * headcount if pass_usd is not None else None, "scraped", url, t,
                                  f"{headcount} passes; {pass_note}".strip("; ")),
        "booth_price_usd": (sourced(booth_usd, "scraped", url, t, booth_note) if booth_usd is not None else
                            sourced(BOOTH_DEFAULT_USD.get(region, 15000), "estimated", None, t,
                                    "not published; team default for a standard booth")),
        "travel_est_usd": sourced(travel_usd, "estimated", None, t,
                                  f"travel_estimates.csv: {headcount} x {tr['per_person_usd']}"),
    }
    if pass_usd is None:
        costs["pass_price_usd"] = sourced(1500 * headcount, "estimated", None, t, "price not published; $1,500/pass default")

    print(f"  ✓ {series}: {info.get('start_date')} {info.get('city')} {cc} | "
          f"{len(sponsors)} sponsors/exhibitors, {len(speakers)} speakers, {len(prior_exhibitors)} prior-yr")
    return {
        "event_id": slug(f"{series}-{info.get('edition_year') or 'unknown'}"),
        "series": series,
        "name": (sourced(info["name"], "scraped", url, t) if info.get("name")
                 else sourced(series, "seed", None, t, "page gave no name; using seed series name")),
        "edition_year": info.get("edition_year"),
        "start_date": sourced(info.get("start_date"), "scraped", url, t),
        "end_date": sourced(info.get("end_date"), "scraped", url, t),
        "city": sourced(info.get("city"), "scraped", url, t),
        "country": sourced(cc or None, "scraped", url, t),
        "region": region,
        "url": url,
        "topics": [x.strip() for x in seed["topics"].split(";") if x.strip()],
        "costs": costs,
        "sponsors": sponsors,
        "exhibitors_prior_year": prior_exhibitors,
        "speakers": speakers,
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--retry-incomplete", action="store_true",
                    help="re-scrape series missing from, or undated in, the latest cache and merge")
    args = ap.parse_args()

    seeds = list(csv.DictReader(open(DATA / "event_seeds.csv")))
    keep: list[dict] = []
    undated_prev: dict = {}
    if args.retry_incomplete and cache.latest():
        prev = cache.latest()["events"]
        hints = {sd["series"]: sd["region_hint"] for sd in seeds}
        # Complete = dated AND still passes validation (wrong-edition entries get retried).
        keep = [e for e in prev if e["start_date"]["value"] and not reject_reason(
            e["series"], hints.get(e["series"], ""), e["name"]["value"], e["region"], e["url"], e.get("edition_year"))]
        done = {e["series"] for e in keep}
        seeds = [sd for sd in seeds if sd["series"] not in done]
        undated_prev = {e["series"]: e for e in prev if e["series"] not in done}
        print(f"Keeping {len(keep)} dated events; retrying {len(seeds)} series")
    if args.limit:
        seeds = seeds[: args.limit]
    travel = {r["dest_region"]: r for r in csv.DictReader(open(DATA / "travel_estimates.csv"))}

    def safe(seed):
        try:
            return discover_one(seed, travel)
        except Exception as e:  # one bad site shouldn't sink the run
            print(f"  ! {seed['series']}: {type(e).__name__}: {e}")
            return None

    with ThreadPoolExecutor(max_workers=6) as pool:
        events = [e for e in pool.map(safe, seeds) if e]
    if args.retry_incomplete:
        # A failed (or --limit-skipped) retry keeps whatever the previous cache had for that series.
        got = {e["series"] for e in events}
        events = keep + events + [e for sr, e in undated_prev.items() if sr not in got]

    if not events:
        print("No events scraped; keeping previous cache:", cache.latest() is not None)
        sys.exit(1)
    print("Wrote", cache.write(events), f"({len(events)} events)")


if __name__ == "__main__":
    main()
