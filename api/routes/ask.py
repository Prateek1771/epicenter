"""POST /ask: question → answer + the graph path it rests on (API.md, HLD §3.2). Needs the LLM: 502 without it."""

import asyncio

from fastapi import APIRouter, Request

from api.ai.openrouter import LLMUnavailable
from api.models import AskIn, AskOut
from api.routes.deps import ApiError, Env, env_name, incident_or_404

router = APIRouter()


@router.post("/ask", response_model=AskOut)
async def ask(body: AskIn, env: Env, request: Request) -> AskOut:
    if body.incident_id:
        incident_or_404(env, body.incident_id)
    try:
        # the agent is sync (httpx + graph calls); keep it off the event loop
        out = await asyncio.to_thread(request.app.state.ask, body.question, env_name(env), body.incident_id)
    except LLMUnavailable as e:
        raise ApiError(502, "UPSTREAM_ERROR", f"LLM unavailable: {e}") from e
    return AskOut(**out)
