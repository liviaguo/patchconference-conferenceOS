from __future__ import annotations

from functools import lru_cache

from falkordb import FalkorDB

from conferenceos import config


@lru_cache(maxsize=1)
def get_db() -> FalkorDB:
    return FalkorDB(
        host=config.FALKORDB_HOST,
        port=config.FALKORDB_PORT,
        username=config.FALKORDB_USERNAME,
        password=config.FALKORDB_PASSWORD,
        ssl=config.FALKORDB_TLS,
    )


def get_graph():
    return get_db().select_graph(config.FALKORDB_GRAPH)


def query(cypher: str, params: dict | None = None) -> list[dict]:
    """Run Cypher and return rows as dicts keyed by column name."""
    res = get_graph().query(cypher, params or {})
    cols = [h[1] if isinstance(h, (list, tuple)) else h for h in res.header]
    return [dict(zip(cols, row)) for row in res.result_set]
