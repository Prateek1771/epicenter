"""GET /health: FalkorDB, falkordb-mcp, OpenRouter (GPT-4o + Jev), OpenConnector, and per-query p50/p95 (HLD §10)."""

import time
import urllib.error
import urllib.request

from fastapi import APIRouter, Request

from api.config import get_settings
from api.graph import query_stats
from api.models import Health

router = APIRouter()

PROBE_TIMEOUT_S = 2.0
OPENROUTER_TTL_S = 60.0
_openrouter_cache: dict = {"at": 0.0, "status": None}


def probe(url: str | None, headers: dict | None = None, any_status: bool = True) -> str:
    """Reachable → ok. With `any_status`, an HTTP error still counts (the MCP endpoint answers a bare GET with 4xx)."""
    if not url:
        return "not_configured"
    try:
        urllib.request.urlopen(urllib.request.Request(url, headers=headers or {}), timeout=PROBE_TIMEOUT_S).close()
        return "ok"
    except urllib.error.HTTPError:
        return "ok" if any_status else "down"
    except (urllib.error.URLError, OSError):
        return "down"


def openrouter_status() -> str:
    """`GET /v1/key` checks the key without spending anything; cached so a polling UI doesn't hammer OpenRouter."""
    s = get_settings()
    if not s.openrouter_api_key:
        return "not_configured"
    now = time.monotonic()
    if _openrouter_cache["status"] is None or now - _openrouter_cache["at"] > OPENROUTER_TTL_S:
        url = f"{s.openrouter_url.rstrip('/')}/v1/key"
        _openrouter_cache.update(
            at=now, status=probe(url, {"Authorization": f"Bearer {s.openrouter_api_key}"}, any_status=False)
        )
    return _openrouter_cache["status"]


@router.get("/health", response_model=Health)
def health(request: Request) -> Health:
    s = get_settings()
    ok = request.app.state.graph.ping()
    oc = f"{s.openconnector_url.rstrip('/')}/health" if s.openconnector_url else None
    llm = openrouter_status()
    return Health(
        status="ok" if ok else "degraded",  # only FalkorDB is required for a verdict (N7)
        falkordb="ok" if ok else "down",
        falkordb_mcp=probe(s.falkordb_mcp_url),
        openrouter=llm,
        jev=llm,  # same OpenRouter key and endpoint family
        openconnector=probe(oc),
        query_ms=query_stats(),
    )
