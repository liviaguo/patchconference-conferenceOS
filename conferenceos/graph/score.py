from __future__ import annotations

from pathlib import Path

from conferenceos import config
from conferenceos.graph import client

SCORE_CYPHER = (Path(__file__).parent / "queries" / "score.cypher").read_text()


def score_events(graph=None, regions=None, date_from=None, date_to=None) -> list[dict]:
    params = {"regions": regions or config.REGIONS, "from": date_from or config.DATE_FROM,
              "to": date_to or config.DATE_TO}
    if graph is None:
        return client.query(SCORE_CYPHER, params)
    res = graph.query(SCORE_CYPHER, params)
    cols = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
    return [dict(zip(cols, row)) for row in res.result_set]
