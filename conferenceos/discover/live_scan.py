"""Live account scan: one Bright Data SERP call per ICP account, then an LLM that may only report a
company-at-event link it can quote verbatim from those search results. Fast enough to run on stage.
"""
from __future__ import annotations

import json
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from openai import OpenAI

from conferenceos import config
from conferenceos.config import STATE_DIR
from conferenceos.discover import brightdata, cache

EVIDENCE_FILE = STATE_DIR / "live_evidence.json"

# Short names people actually write in press releases and speaker bios
SHORT = {
    "SLAS International Conference": "SLAS2027", "Bio-IT World Conference & Expo": "Bio-IT World",
    "BIO-Europe Spring": "BIO-Europe Spring", "BIO International Convention": "BIO International",
    "AACR Annual Meeting": "AACR", "Pittcon": "Pittcon", "PEGS Boston": "PEGS Boston",
    "ASGCT Annual Meeting": "ASGCT", "Biotech Showcase": "Biotech Showcase",
    "Festival of Genomics": "Festival of Genomics", "Society of Toxicology Annual Meeting": "ToxExpo",
}

PROMPT = """You verify whether a company will be at specific 2027 conferences, using ONLY the search
results given. Return JSON {"matches": [{"event_id": str, "relation": "sponsor"|"exhibitor"|"speaker",
"person": str|null, "result": int, "quote": str}]}.
Rules: include a match only if a result's title or snippet explicitly ties THIS company to THAT event's
2027 edition (sponsoring, exhibiting, or a named person from the company speaking). News about the
company that merely mentions the event, or lists from 2026 or earlier, do NOT count.
"quote" must be copied verbatim from that result's title or snippet and must itself contain both the
company name and the event name. "speaker" requires the person's name, also inside the quote.
If nothing qualifies, return {"matches": []}. Never guess."""


def load_evidence() -> list[dict]:
    return json.loads(EVIDENCE_FILE.read_text()) if EVIDENCE_FILE.exists() else []


def save_evidence(items: list[dict]) -> None:
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    EVIDENCE_FILE.write_text(json.dumps(items, indent=2))


def _query(account: str, events: list[dict]) -> str:
    names = " OR ".join(f'"{SHORT.get(e["series"], e["series"])}"' for e in events)
    return f'"{account}" 2027 ({names})'


def scan_account(account: str, events: list[dict]) -> dict:
    """Returns {account, query, n_results, seconds, matches:[evidence...], error}."""
    t0 = time.time()
    q = _query(account, events)
    try:
        results = brightdata.serp(q, num=10, attempts=2, timeout=30)  # on stage: one quick retry
    except Exception as ex:
        return {"account": account, "query": q, "n_results": 0, "seconds": time.time() - t0,
                "matches": [], "error": "Bright Data search didn't return in time; select it and scan again"
                if "timed out" in str(ex) or str(ex).startswith("200") else f"Bright Data: {ex}"}
    if not results:
        return {"account": account, "query": q, "n_results": 0, "seconds": time.time() - t0, "matches": []}

    listing = [{"i": i, "title": r["title"], "snippet": r["description"], "url": r["link"]} for i, r in enumerate(results)]
    resp = OpenAI(api_key=config.OPENAI_API_KEY).chat.completions.create(
        model=config.OPENAI_MODEL, temperature=0, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": PROMPT},
                  {"role": "user", "content": json.dumps({
                      "company": account,
                      "events": [{"event_id": e["event_id"], "name": e["series"], "aka": SHORT.get(e["series"])} for e in events],
                      "results": listing})}],
    )
    ids = {e["event_id"]: e for e in events}
    matches, now = [], cache.now_iso()
    for m in json.loads(resp.choices[0].message.content).get("matches", []):
        r = listing[m["result"]] if isinstance(m.get("result"), int) and 0 <= m["result"] < len(listing) else None
        text = f"{r['title']} {r['snippet']}".lower() if r else ""
        quote = (m.get("quote") or "").lower()
        ev = ids.get(m.get("event_id"))
        alias = (SHORT.get(ev["series"], ev["series"]) if ev else "").lower()
        # Keep only what we can check ourselves: verbatim quote that names company AND event (AND person)
        if (r and ev and quote and quote in text and "2027" in quote  # the quote itself must be about 2027
                and account.split()[0].lower() in quote
                and (alias in quote or ev["series"].lower() in quote or alias.replace("2027", "") in quote)
                and m.get("relation") in ("sponsor", "exhibitor", "speaker")
                and (m["relation"] != "speaker" or (m.get("person") and m["person"].split()[-1].lower() in quote))):
            matches.append({"account": account, "event_id": m["event_id"], "event": ids[m["event_id"]]["series"],
                            "relation": m["relation"], "person": m.get("person"), "quote": m["quote"],
                            "source_url": r["url"], "fetched_at": now, "via": "live_scan"})
    return {"account": account, "query": q, "n_results": len(results), "seconds": time.time() - t0, "matches": matches}


def scan(accounts: list[str], events: list[dict], workers: int = 5):  # >5 parallel SERP calls got empty replies
    """Yields each account's result as soon as it finishes (for a live log)."""
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(scan_account, a, events) for a in accounts]
        for f in as_completed(futures):
            yield f.result()
