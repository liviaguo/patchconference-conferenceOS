"""Load the latest event cache + ICP + simulated pipeline into FalkorDB."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos.discover import cache  # noqa: E402
from conferenceos.graph.client import get_graph  # noqa: E402
from conferenceos.graph.load import build  # noqa: E402

doc = cache.latest()
if not doc:
    sys.exit("No data/cache/events_*.json yet; run scripts/discover.py first")
print(build(get_graph(), doc))
