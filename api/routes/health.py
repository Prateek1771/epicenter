"""GET /health: FalkorDB, falkordb-mcp, OpenRouter, OpenConnector, and per-query p50/p95 (HLD §10)."""

import urllib.error
import urllib.request

from fastapi import APIRouter, Request

from api.config import get_settings
from api.graph import query_stats
from api.models import Health

router = APIRouter()

PROBE_TIMEOUT_S = 2.0


def probe(url: str | None) -> str:
    """Reachable at all (any HTTP status) → ok. The MCP endpoint answers a bare GET with 4xx, which still means up."""
    if not url:
        return "not_configured"
    try:
        urllib.request.urlopen(url, timeout=PROBE_TIMEOUT_S).close()
        return "ok"
    except urllib.error.HTTPError:
        return "ok"
    except (urllib.error.URLError, OSError):
        return "down"


@router.get("/health", response_model=Health)
def health(request: Request) -> Health:
    s = get_settings()
    ok = request.app.state.graph.ping()
    oc = f"{s.openconnector_url.rstrip('/')}/health" if s.openconnector_url else None
    return Health(
        status="ok" if ok else "degraded",  # only FalkorDB is required for a verdict (N7)
        falkordb="ok" if ok else "down",
        falkordb_mcp=probe(s.falkordb_mcp_url),
        # ponytail: key presence only; a live OpenRouter call per health check costs money. Real check: phase 7 client.
        openrouter="configured" if s.openrouter_api_key else "not_configured",
        openconnector=probe(oc),
        query_ms=query_stats(),
    )
