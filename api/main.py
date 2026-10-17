"""FastAPI app: REST under /api/v1 (API.md), SSE per incident, the typed tools over MCP at /mcp.

The only module that imports `agents` (AGENTS.md rule 1): routes reach the agent flow through `app.state.diagnosis`.
"""

import asyncio
import json
import logging
import secrets
import threading
from contextlib import asynccontextmanager

from fastapi import APIRouter, FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException

from api.agents import ask, flow
from api.config import get_settings
from api.events import publish
from api.graph import Graph, GraphUnavailable, get_graph
from api.ingest import live
from api.ingest.seed import seed_all
from api.routes import alerts, conversations, deliver, graph_views, health, incidents, runs
from api.routes import ask as ask_route
from api.routes import eval as eval_route
from api.routes.deps import ApiError
from api.runs import Runner
from api.tools import mcp_server

logging.basicConfig(level=logging.INFO, format="%(message)s")
log = logging.getLogger("epicenter.api")


class Diagnosis:
    """Runs the agent flow off the request path (endpoints return 202).

    ponytail: the `running` set is per process, so a second POST while a run is in flight doesn't start a duplicate.
    With more API replicas, take a Redis `SET NX` lock per incident instead.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._running: set[tuple[str, str]] = set()

    def running(self, env: str, incident_id: str) -> bool:
        with self._lock:
            return (env, incident_id) in self._running

    def start(self, env: str, incident_id: str, resume: bool) -> None:
        key = (env, incident_id)
        with self._lock:
            if key in self._running:
                return
            self._running.add(key)
        try:
            v = flow.resume(incident_id, env) if resume else None
            if v is None or v["status"] == "diagnosing":  # nothing to resume (no checkpoint): start a new run
                live.ingest_for_alert(get_graph(), env, incident_id)  # live envs only, once per incident
                flow.run(incident_id, env)
        except Exception as e:
            log.exception(json.dumps({"incident_id": incident_id, "event": "diagnosis_failed"}))
            try:
                publish(f"env:{env}", incident_id, "error", {"code": type(e).__name__, "message": str(e)})
            except GraphUnavailable:
                pass  # the stream lives in FalkorDB too; the incident stays `diagnosing` and can be resumed
        finally:
            with self._lock:
                self._running.discard(key)


@asynccontextmanager
async def lifespan(app: FastAPI):
    s = get_settings()
    app.state.graph = Graph(s.falkordb_url, s.query_timeout_s)
    app.state.diagnosis = Diagnosis()
    app.state.runner = Runner()
    app.state.ask = ask.answer
    try:
        for env in sorted({s.env_name} | live.live_envs()):  # every live env gets its owners and runbooks
            seed_all(app.state.graph, env)
    except GraphUnavailable as e:
        # ponytail: seed runs once per start; restart the api after FalkorDB is back to seed
        log.warning(json.dumps({"event": "seed_skipped", "reason": str(e)}))
    # A session manager runs once, so each startup builds a fresh /mcp app (tests start the app many times)
    mcp_app = mcp_server.asgi_app()
    app.router.routes[:] = [r for r in app.router.routes if getattr(r, "path", None) != "/mcp"] + list(mcp_app.routes)
    ticker = asyncio.create_task(_live_ticks(app.state.graph, s.live_tick_s)) if s.live_tick_s > 0 else None
    try:
        async with mcp_server.server.session_manager.run():  # a mounted sub-app's own lifespan never runs
            yield
    finally:
        if ticker:
            ticker.cancel()


async def _live_ticks(graph: Graph, every_s: int) -> None:
    """Topology roll-up for the live envs, so blast radius and what-if work before any incident.

    ponytail: one loop in the API process; give it its own ingest worker when a second live env runs at once."""
    while True:
        for env in sorted(live.live_envs()):
            try:
                n = await asyncio.to_thread(live.tick, graph, env)
                log.info(json.dumps({"event": "live_tick", "env": env, "rows": n}))
            except Exception as e:  # a down source or graph must not kill the loop
                log.warning(json.dumps({"event": "live_tick_failed", "env": env, "reason": str(e)}))
        await asyncio.sleep(every_s)


app = FastAPI(title="Epicenter", lifespan=lifespan)


def _error(request: Request, status: int, code: str, message: str, details: list | None = None) -> JSONResponse:
    # Error envelope from docs/API.md#errors
    request_id = getattr(request.state, "request_id", None)
    return JSONResponse(
        status_code=status,
        content={"error": {"code": code, "message": message, "details": details or []}, "request_id": request_id},
        headers={"X-Request-ID": request_id} if request_id else None,
    )


@app.middleware("http")
async def request_context(request: Request, call_next):
    request.state.request_id = f"req-{secrets.token_hex(4)}"
    key = get_settings().api_key
    path = request.url.path
    # Deployed mode only: with API_KEY set, every /api/v1 call but /health needs X-API-Key
    if key and path.startswith("/api/v1") and path != "/api/v1/health":
        if not secrets.compare_digest(request.headers.get("X-API-Key", ""), key):
            return _error(request, 401, "UNAUTHORIZED", "Missing or wrong X-API-Key")
    response = await call_next(request)
    response.headers["X-Request-ID"] = request.state.request_id
    return response


# Added after the middleware above, so CORS wraps it and a 401 still carries CORS headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=[get_settings().web_origin],
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["X-Request-ID"],
)


@app.exception_handler(ApiError)
async def api_error(request: Request, exc: ApiError) -> JSONResponse:
    return _error(request, exc.status, exc.code, exc.message)


@app.exception_handler(HTTPException)
async def http_error(request: Request, exc: HTTPException) -> JSONResponse:
    code = exc.detail if isinstance(exc.detail, str) and exc.detail.isupper() else "HTTP_ERROR"
    return _error(request, exc.status_code, code, str(exc.detail))


@app.exception_handler(RequestValidationError)
async def validation_error(request: Request, exc: RequestValidationError) -> JSONResponse:
    return _error(request, 400, "VALIDATION_ERROR", "Bad body or query parameter", jsonable(exc.errors()))


@app.exception_handler(GraphUnavailable)
async def graph_unavailable(request: Request, exc: GraphUnavailable) -> JSONResponse:
    return _error(request, 503, "GRAPH_UNAVAILABLE", "FalkorDB unreachable")


def jsonable(errors: list) -> list:
    return [{"loc": list(e.get("loc", [])), "msg": e.get("msg", "")} for e in errors]


router = APIRouter(prefix="/api/v1")
for r in (health, alerts, incidents, deliver, ask_route, conversations, graph_views, runs, eval_route):
    router.include_router(r.router)
app.include_router(router)
