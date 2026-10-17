"""POST /ask: question → answer + the graph path it rests on (API.md, HLD §3.2). Needs the LLM: 502 without it.

With `conversation_id` the question and the answer are saved as Messages (routes/conversations.py) and the last turns
go to the model as history; the question is saved before the model is called, so a 502 still leaves it in the thread.
"""

import asyncio

from fastapi import APIRouter, Request

from api.ai.openrouter import LLMUnavailable
from api.models import AskIn, AskOut
from api.routes import conversations as conv
from api.routes.deps import ApiError, Env, env_name, incident_or_404

router = APIRouter()


@router.post("/ask", response_model=AskOut)
async def ask(body: AskIn, env: Env, request: Request) -> AskOut:
    if body.incident_id:
        incident_or_404(env, body.incident_id)
    past: list[dict] = []
    if body.conversation_id:
        conv.conversation_or_404(env, body.conversation_id)
        past = conv.history(env, body.conversation_id)
        names = [a.name for a in body.attachments]
        conv.add_message(env, body.conversation_id, "user", body.question, attachments=names)
        env.rw("conv_title", id=body.conversation_id, title=conv.title_of(body.question))
    files = [a.model_dump() for a in body.attachments]
    try:
        # the agent is sync (httpx + graph calls); keep it off the event loop
        out = await asyncio.to_thread(
            request.app.state.ask, body.question, env_name(env), body.incident_id, history=past, attachments=files
        )
    except LLMUnavailable as e:
        raise ApiError(502, "UPSTREAM_ERROR", f"LLM unavailable: {e}") from e
    res = AskOut(**out, conversation_id=body.conversation_id)
    if body.conversation_id:
        res.message_id = conv.add_message(
            env,
            body.conversation_id,
            "assistant",
            res.answer,
            path=res.path,
            tools=[t.model_dump() for t in res.tools_used],
            cypher=res.cypher,
        )
    return res
