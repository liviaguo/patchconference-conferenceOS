"""LLM extraction of event facts from scraped markdown. Never guesses: missing -> null."""
from __future__ import annotations

import json

from openai import OpenAI

from conferenceos import config

MAX_CHARS = 60_000

PROMPT = """You extract facts about a conference from scraped web page text.
Return JSON only, with these keys:
{
  "name": str|null,
  "edition_year": int|null,
  "start_date": "YYYY-MM-DD"|null,
  "end_date": "YYYY-MM-DD"|null,
  "city": str|null,
  "country_code": ISO-3166 alpha-2|null,
  "pass_price": {"amount": number, "currency": "USD"|"EUR"|"GBP"|"CHF", "label": str}|null,
  "booth_price": {"amount": number, "currency": str, "label": str}|null,
  "sponsors": [{"name": str, "tier": str|null}],
  "exhibitors": [str],
  "speakers": [{"name": str, "title": str|null, "company": str|null}]
}
Rules: only use facts stated in the text. If something is not stated, use null or [].
Do not infer dates from previous years. pass_price = cheapest full industry/commercial
registration (not student/academic). Keep lists to at most 150 items."""


def extract_event(markdown: str, source_url: str) -> dict:
    client = OpenAI(api_key=config.OPENAI_API_KEY)
    resp = client.chat.completions.create(
        model=config.OPENAI_MODEL,
        response_format={"type": "json_object"},
        temperature=0,
        messages=[
            {"role": "system", "content": PROMPT},
            {"role": "user", "content": f"SOURCE: {source_url}\n\n{markdown[:MAX_CHARS]}"},
        ],
    )
    return json.loads(resp.choices[0].message.content)
