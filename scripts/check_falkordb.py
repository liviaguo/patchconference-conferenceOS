"""Smoke test: connect to FalkorDB and round-trip one node."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from conferenceos import config  # noqa: E402
from conferenceos.graph.client import get_db  # noqa: E402

g = get_db().select_graph("conferenceos_smoke")
g.query("MERGE (n:Ping {id: 1}) SET n.at = timestamp()")
print("FalkorDB OK:", config.FALKORDB_HOST, g.query("MATCH (n:Ping) RETURN n.id").result_set)
g.delete()
