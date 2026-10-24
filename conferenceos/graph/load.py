"""Load cache + seeds into FalkorDB. Rebuilds the graph from scratch each run."""
from __future__ import annotations

import csv
import re

from conferenceos.config import DATA

SUFFIXES = r"\b(inc|incorporated|corp|corporation|co|ltd|limited|plc|ag|sa|se|nv|gmbh|llc|holdings|group)\b\.?"


def company_key(name: str) -> str:
    """Normalized company name used to match scraped names to ICP accounts."""
    s = re.sub(r"[^a-z0-9 ]+", " ", (name or "").lower())
    s = re.sub(SUFFIXES, " ", s)
    return re.sub(r"\s+", "", s)  # "ThermoFisher" == "Thermo Fisher"


def load_accounts() -> list[dict]:
    return list(csv.DictReader(open(DATA / "icp_accounts.csv")))


def alias_map(accounts: list[dict]) -> dict[str, str]:
    """Any known name/alias key -> canonical account key."""
    m = {}
    for a in accounts:
        canon = company_key(a["name"])
        for n in [a["name"]] + [x for x in (a.get("aliases") or "").split(";") if x]:
            m[company_key(n)] = canon
    return m


def build(graph, cache_doc: dict) -> dict:
    accounts = load_accounts()
    aliases = alias_map(accounts)

    def ckey(name: str) -> str:
        k = company_key(name)
        return aliases.get(k, k)

    try:
        graph.delete()
    except Exception:
        pass  # graph didn't exist yet
    for stmt in ("CREATE INDEX FOR (e:Event) ON (e.event_id)",
                 "CREATE INDEX FOR (c:Company) ON (c.key)",
                 "CREATE INDEX FOR (p:Person) ON (p.person_id)"):
        graph.query(stmt)

    graph.query("UNWIND ['US','EU','OTHER'] AS code MERGE (:Region {code: code})")

    graph.query(
        """UNWIND $rows AS a
           MERGE (c:Company {key: a.key})
           SET c:Account, c.name = a.name, c.account_id = a.account_id, c.domain = a.domain,
               c.segment = a.segment, c.tier = toInteger(a.tier), c.hq_region = a.region""",
        {"rows": [dict(a, key=company_key(a["name"])) for a in accounts]},
    )

    opps = list(csv.DictReader(open(DATA / "synthetic" / "pipeline.csv")))
    graph.query(
        """UNWIND $rows AS o
           MATCH (a:Account {account_id: o.account_id})
           MERGE (op:Opportunity {opp_id: o.opp_id})
           SET op.stage = o.stage, op.amount_usd = toInteger(o.amount_usd), op.simulated = true
           MERGE (a)-[:IN_PIPELINE {simulated: true}]->(op)""",
        {"rows": opps},
    )

    events, sponsors, attends, speakers, topics = [], [], [], [], []
    for e in cache_doc["events"]:
        c = e["costs"]
        events.append({
            # Scraped names can be generic ("2027 Annual Meeting"); display series + year instead.
            "event_id": e["event_id"], "name": f"{e['series']} {e.get('edition_year') or ''}".strip(),
            "official_name": e["name"]["value"], "series": e["series"],
            "start_date": e["start_date"]["value"] or "", "end_date": e["end_date"]["value"] or "",
            "city": e["city"]["value"] or "", "country": e["country"]["value"] or "",
            "region": e["region"], "url": e["url"], "fetched_at": e["name"]["fetched_at"],
            "pass_price": c["pass_price_usd"]["value"], "pass_price_prov": c["pass_price_usd"]["prov"],
            "pass_price_note": c["pass_price_usd"]["note"],
            "booth_price": c["booth_price_usd"]["value"], "booth_price_prov": c["booth_price_usd"]["prov"],
            "booth_price_note": c["booth_price_usd"]["note"],
            "travel_est": c["travel_est_usd"]["value"], "travel_est_prov": c["travel_est_usd"]["prov"],
            "travel_est_note": c["travel_est_usd"]["note"],
        })
        for t in e["topics"]:
            topics.append({"event_id": e["event_id"], "topic": t})
        for s in e["sponsors"]:
            if s.get("name"):
                sponsors.append({"event_id": e["event_id"], "key": ckey(s["name"]), "name": s["name"],
                                 "tier": s.get("tier") or "", "prov": s["prov"], "source_url": s.get("source_url") or ""})
        for x in e["exhibitors_prior_year"]:
            if x.get("name"):
                attends.append({"event_id": e["event_id"], "key": ckey(x["name"]), "name": x["name"],
                                "prov": x["prov"], "basis": x["basis"], "source_url": x.get("source_url") or ""})
        for p in e["speakers"]:
            if p.get("name"):
                speakers.append({"event_id": e["event_id"], "person_id": company_key(p["name"]) + "|" + ckey(p.get("company") or ""),
                                 "name": p["name"], "title": p.get("title") or "", "company": p.get("company") or "",
                                 "key": ckey(p.get("company") or ""), "prov": p["prov"], "source_url": p.get("source_url") or ""})

    graph.query(
        """UNWIND $rows AS e
           MERGE (ev:Event {event_id: e.event_id})
           SET ev += e
           WITH ev, e MATCH (r:Region {code: e.region}) MERGE (ev)-[:IN_REGION]->(r)""",
        {"rows": events},
    )
    graph.query(
        """UNWIND $rows AS t MATCH (e:Event {event_id: t.event_id})
           MERGE (tp:Topic {name: t.topic}) MERGE (e)-[:ABOUT_TOPIC]->(tp)""",
        {"rows": topics},
    )
    graph.query(
        """UNWIND $rows AS s MATCH (e:Event {event_id: s.event_id})
           MERGE (c:Company {key: s.key}) ON CREATE SET c.name = s.name
           MERGE (c)-[r:SPONSORS]->(e)
           // several brands can map to one account (Cytiva, Beckman -> Danaher): keep every name, and the
           // strongest tier, instead of letting the last row overwrite the evidence
           SET r.as_name = CASE WHEN r.as_name IS NULL OR r.as_name = s.name THEN s.name
                                WHEN r.as_name CONTAINS s.name THEN r.as_name ELSE r.as_name + '; ' + s.name END,
               r.tier = CASE WHEN r.tier IS NULL OR r.tier IN ['', 'exhibitor'] THEN s.tier ELSE r.tier END,
               r.prov = s.prov, r.source_url = s.source_url""",
        {"rows": sponsors},
    )
    graph.query(
        """UNWIND $rows AS s MATCH (e:Event {event_id: s.event_id})
           MERGE (c:Company {key: s.key}) ON CREATE SET c.name = s.name
           MERGE (c)-[r:ATTENDS]->(e)
           SET r.as_name = CASE WHEN r.as_name IS NULL OR r.as_name = s.name THEN s.name
                                WHEN r.as_name CONTAINS s.name THEN r.as_name ELSE r.as_name + '; ' + s.name END,
               r.prov = s.prov, r.basis = s.basis, r.source_url = s.source_url""",
        {"rows": attends},
    )
    graph.query(
        """UNWIND $rows AS s MATCH (e:Event {event_id: s.event_id})
           MERGE (p:Person {person_id: s.person_id}) SET p.name = s.name, p.title = s.title
           MERGE (p)-[r:SPEAKS_AT]->(e) SET r.prov = s.prov, r.source_url = s.source_url
           WITH p, s WHERE s.key <> ''
           MERGE (c:Company {key: s.key}) ON CREATE SET c.name = s.company
           MERGE (p)-[:WORKS_AT {prov: s.prov}]->(c)""",
        {"rows": speakers},
    )
    return {"events": len(events), "sponsor_edges": len(sponsors), "attend_edges": len(attends),
            "speakers": len(speakers), "accounts": len(accounts), "opportunities": len(opps)}
