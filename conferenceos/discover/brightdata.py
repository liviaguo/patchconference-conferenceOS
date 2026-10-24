"""Bright Data REST client (Web Unlocker + SERP via POST /request)."""
from __future__ import annotations

from urllib.parse import quote_plus

import requests

from conferenceos import config

API = "https://api.brightdata.com/request"


class BrightDataError(RuntimeError):
    pass


def _request(payload: dict, timeout: int = 90, attempts: int = 3) -> requests.Response:
    if not config.BRIGHTDATA_API_KEY:
        raise BrightDataError("BRIGHTDATA_API_KEY not set")
    last = ""
    for _ in range(attempts):
        try:
            r = requests.post(
                API,
                headers={"Authorization": f"Bearer {config.BRIGHTDATA_API_KEY}"},
                json=payload,
                timeout=timeout,
            )
        except requests.RequestException as e:
            last = str(e)
            continue
        if r.status_code == 200 and r.text.strip():
            return r
        last = f"{r.status_code}: {r.text[:200]}"
        if r.status_code < 500 and r.status_code != 200:
            break  # client errors won't fix themselves
    raise BrightDataError(last)


def serp(query: str, num: int = 10, attempts: int = 3) -> list[dict]:
    """Google organic results: [{title, link, description}]."""
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&brd_json=1"
    for _ in range(attempts):
        try:
            data = _request({"url": url, "zone": config.BRIGHTDATA_SERP_ZONE, "format": "raw"}).json()
            break
        except ValueError:  # occasionally returns HTML instead of parsed JSON
            continue
    else:
        raise BrightDataError(f"SERP returned non-JSON for {query!r}")
    return [
        {"title": o.get("title"), "link": o.get("link"), "description": o.get("description")}
        for o in data.get("organic", [])
    ]


def unlock(url: str) -> str:
    """Fetch a page as markdown."""
    return _request(
        {"url": url, "zone": config.BRIGHTDATA_UNLOCKER_ZONE, "format": "raw", "data_format": "markdown"}
    ).text
