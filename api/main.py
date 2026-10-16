"""FastAPI app: REST under /api/v1. SSE and the /mcp mount arrive in phases 5 and 6."""

import json
import logging
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from api.config import get_settings
from api.graph import Graph, GraphUnavailable, query_stats
from api.ingest.seed import seed_all

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("epicenter.api")


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.graph = Graph(s.falkordb_url, s.query_timeout_s)
    try:
        seed_all(app.state.graph, s.env_name)
    except GraphUnavailable as e:
        # ponytail: seed runs once per start; restart the api after FalkorDB is back to seed
        log.warning(json.dumps({"event": "seed_skipped", "reason": str(e)}))
    yield


app = FastAPI(title="Epicenter", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=[get_settings().web_origin], allow_methods=["*"], allow_headers=["*"])


def _error(status: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    # Error envelope from docs/API.md#errors
    return JSONResponse(
        status_code=status, content={"error": {"code": code, "message": message, "details": details or []}}
    )


@app.exception_handler(HTTPException)
async def http_error(_: Request, exc: HTTPException) -> JSONResponse:
    code = exc.detail if isinstance(exc.detail, str) and exc.detail.isupper() else "HTTP_ERROR"
    return _error(exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(_: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(400, "VALIDATION_ERROR", "Bad body or query parameter", jsonable(exc.errors()))


@app.exception_handler(GraphUnavailable)
async def graph_unavailable(_: Request, exc: GraphUnavailable) -> JSONResponse:
    return _error(503, "GRAPH_UNAVAILABLE", "FalkorDB unreachable")


def jsonable(errors: list) -> list:
    return [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in errors]


router = APIRouter(prefix="/api/v1")


@router.get("/health")
def health(request: Request) -> dict:
    # ponytail: only FalkorDB so far; falkordb_mcp/openrouter/openconnector join in phases 5–7
    ok = request.app.state.graph.ping()
    return {"status": "ok" if ok else "degraded", "falkordb": "ok" if ok else "down", "query_ms": query_stats()}


app.include_router(router)
