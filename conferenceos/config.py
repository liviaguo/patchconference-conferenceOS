"""Settings loaded from .env. Python 3.9-compatible (only 3.9 is installed locally)."""
from __future__ import annotations

import os
from pathlib import Path

from dotenv import load_dotenv

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
CACHE_DIR = DATA / "cache"
STATE_DIR = DATA / "state"

load_dotenv(ROOT / ".env")

# Demo scope
DATE_FROM = "2027-01-01"
DATE_TO = "2027-06-30"
REGIONS = ["US", "EU"]  # EU = Europe incl. UK/CH


def env(name: str, default: str = "") -> str:
    return os.getenv(name, default)


FALKORDB_HOST = env("FALKORDB_HOST", "localhost")
FALKORDB_PORT = int(env("FALKORDB_PORT", "6379"))
FALKORDB_USERNAME = env("FALKORDB_USERNAME") or None
FALKORDB_PASSWORD = env("FALKORDB_PASSWORD") or None
FALKORDB_TLS = env("FALKORDB_TLS", "false").lower() == "true"
FALKORDB_GRAPH = env("FALKORDB_GRAPH", "conferenceos")

BRIGHTDATA_API_KEY = env("BRIGHTDATA_API_KEY")
BRIGHTDATA_UNLOCKER_ZONE = env("BRIGHTDATA_UNLOCKER_ZONE", "cli_unlocker")
BRIGHTDATA_SERP_ZONE = env("BRIGHTDATA_SERP_ZONE", "cli_unlocker")

OPENAI_API_KEY = env("OPENAI_API_KEY")
OPENAI_MODEL = env("OPENAI_MODEL", "gpt-4o-mini")
TRUEFORGE_API_KEY = env("TRUEFORGE_API_KEY")
