"""The only module that talks to FalkorDB (AGENTS.md rule 2). Phase 1 adds EnvGraph and the QUERIES catalogue."""

from falkordb import FalkorDB


class Graph:
    def __init__(self, url: str, timeout_s: float = 5.0):
        self._db = FalkorDB.from_url(url, socket_timeout=timeout_s, socket_connect_timeout=timeout_s)

    def ping(self) -> bool:
        try:
            return bool(self._db.connection.ping())
        except Exception:
            return False
