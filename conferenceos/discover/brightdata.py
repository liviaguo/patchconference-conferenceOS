"""Bright Data REST client (Web Unlocker + SERP via POST /request)."""
from __future__ import annotations

from urllib.parse import quote_plus

import requests

from conferenceos import config

API = "https://api.brightdata.com/request"


class BrightDataError(RuntimeError):
    pass


def _request(payload: dict, timeout: int = 90) -> requests.Response:
    if not config.BRIGHTDATA_API_KEY:
        raise BrightDataError("BRIGHTDATA_API_KEY not set")
    r = requests.post(
        API,
        headers={"Authorization": f"Bearer {config.BRIGHTDATA_API_KEY}"},
        json=payload,
        timeout=timeout,
    )
    if r.status_code != 200:
        raise BrightDataError(f"{r.status_code}: {r.text[:200]}")
    return r


def serp(query: str, num: int = 10) -> list[dict]:
    """Google organic results: [{title, link, description}]."""
    url = f"https://www.google.com/search?q={quote_plus(query)}&num={num}&brd_json=1"
    data = _request({"url": url, "zone": config.BRIGHTDATA_SERP_ZONE, "format": "raw"}).json()
    return [
        {"title": o.get("title"), "link": o.get("link"), "description": o.get("description")}
        for o in data.get("organic", [])
    ]


def unlock(url: str) -> str:
    """Fetch a page as markdown."""
    return _request(
        {"url": url, "zone": config.BRIGHTDATA_UNLOCKER_ZONE, "format": "raw", "data_format": "markdown"}
    ).text
