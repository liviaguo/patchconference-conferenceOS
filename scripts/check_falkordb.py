"""Smoke test: connect to FalkorDB and round-trip one node in a throwaway graph."""
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos import config  # noqa: E402
from conferenceos.graph.client import get_db  # noqa: E402

# Unique name so we never delete a graph that already existed.
name = f"conferenceos_smoke_{uuid.uuid4().hex[:8]}"
g = get_db().select_graph(name)
try:
    g.query("CREATE (n:Ping {id: 1})")
    print("FalkorDB OK:", config.FALKORDB_HOST, g.query("MATCH (n:Ping) RETURN n.id").result_set)
finally:
    g.delete()
