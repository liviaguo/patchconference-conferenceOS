"""Draft CS/Sales outreach for each ICP account present at an event, grounded in its graph path."""
from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

from conferenceos import config

SYSTEM = """You draft short pre-conference outreach emails for LabFlow, an R&D data platform for
life-science teams (ELN, LIMS, workflow automation). Audience: the named target account.
Use ONLY the facts given (event, dates, city, and how the account is connected to the event).
Do not invent names, numbers, customer logos, or meeting slots. Pipeline data is simulated and
must never appear in the email. Connections ending "(estimated)" with ATTENDS mean the company
exhibited at the PREVIOUS edition only: do not claim they are attending this year; say they were
there last year and ask whether they'll be there. "(scraped)" connections come from this edition's
event pages: SPONSORS = sponsoring, EXHIBITS_AT = exhibiting (never call an exhibitor a sponsor),
SPEAKS_AT = a named person is speaking (mention that person). Return JSON: {"subject": str, "body": str, "owner": "CS"|"Sales",
"rationale": str}. Body: under 120 words, ends with a request for a 20-minute meeting at the event."""


def _evidence_for(account: str, why: list[str]) -> list[str]:
    return [w for w in why if w.startswith(account + " ")]


def draft_one(event: dict, account: str, has_open_opp: bool) -> dict:
    facts = {
        "event": event["event"], "start_date": event["start_date"], "city": event["city"],
        "account": account, "connections": _evidence_for(account, event["why"]),
        "suggested_owner": "Sales" if has_open_opp else "CS",
    }
    resp = OpenAI(api_key=config.OPENAI_API_KEY).chat.completions.create(
        model=config.OPENAI_MODEL, temperature=0.4, response_format={"type": "json_object"},
        messages=[{"role": "system", "content": SYSTEM}, {"role": "user", "content": json.dumps(facts)}],
    )
    out = json.loads(resp.choices[0].message.content)
    # owner is decided by our data (open simulated opportunity -> Sales), not by the model
    out.update(account=account, evidence=facts["connections"], owner=facts["suggested_owner"])
    return out


def draft_batch(event: dict, accounts_with_opps: set[str]) -> list[dict]:
    def safe(a: str) -> dict:
        try:
            return draft_one(event, a, a in accounts_with_opps)
        except Exception as ex:  # one failed account shouldn't discard the whole batch
            return {"account": a, "subject": "", "body": "", "owner": "Sales" if a in accounts_with_opps else "CS",
                    "evidence": _evidence_for(a, event["why"]), "error": f"{type(ex).__name__}: {ex}",
                    "rationale": "Draft failed; write manually or redraft."}

    with ThreadPoolExecutor(max_workers=6) as pool:
        return list(pool.map(safe, event["accounts"]))
