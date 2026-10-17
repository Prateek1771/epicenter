"""Ask conversations (API.md): shared, per env, kept in the graph so every viewer and device sees the same history.

A conversation is created first (POST /conversations), so the client holds its id even when the LLM is down; POST /ask
with `conversation_id` then saves the question and the answer as Message nodes. Attachments are never stored, only
their names.
"""

import json
import time
from typing import Annotated

from fastapi import APIRouter, Query

from api.graph import EnvGraph
from api.models import ConversationDetail, ConversationIn, ConversationOut, Conversations, MessageOut, ToolUse
from api.routes.deps import ApiError, Env, decode_cursor, encode_cursor, incident_or_404, iso

router = APIRouter()

HISTORY_TURNS = 6  # messages sent back to the model as context
TITLE_CHARS = 60


def title_of(question: str) -> str:
    """The first question, one line, cut on a word: no LLM call spent on a title."""
    one = " ".join(question.split())
    return one if len(one) <= TITLE_CHARS else one[:TITLE_CHARS].rsplit(" ", 1)[0] + "…"


def _out(r: dict) -> ConversationOut:
    return ConversationOut(
        id=r["id"],
        title=r["title"] or "New chat",
        incident=r["incident"],
        created=iso(r["created"]),
        updated=iso(r["updated"]),
        messages=r["n"] or 0,
    )


def conversation_or_404(env: EnvGraph, conv: str) -> dict:
    [c] = env.ro("conv_get", id=conv) or [None]
    if c is None:
        raise ApiError(404, "CONVERSATION_NOT_FOUND", f"No conversation {conv!r}")
    return c


def history(env: EnvGraph, conv: str) -> list[dict]:
    """The last turns as chat messages for the model (oldest first)."""
    rows = env.ro("conv_messages", conv=conv)[-HISTORY_TURNS:]
    return [{"role": r["role"], "content": r["text"]} for r in rows]


def add_message(env: EnvGraph, conv: str, role: str, text: str, **extra) -> str:
    c = conversation_or_404(env, conv)
    mid = f"{conv}:m{(c['n'] or 0) + 1:04d}"  # sortable within the conversation
    env.rw(
        "msg_add",
        conv=conv,
        id=mid,
        role=role,
        text=text,
        ts=int(time.time()),
        path=extra.get("path", []),
        tools=json.dumps(extra.get("tools", [])),
        cypher=extra.get("cypher"),
        attachments=extra.get("attachments", []),
    )
    return mid


@router.post("/conversations", status_code=201, response_model=ConversationOut)
def create(body: ConversationIn, env: Env) -> ConversationOut:
    if body.incident_id:
        incident_or_404(env, body.incident_id)
    cid = f"conv-{time.time_ns()}"
    env.rw("conv_create", id=cid, title=body.title or "", incident=body.incident_id, ts=int(time.time()))
    if body.incident_id:
        env.rw("conv_about", id=cid, incident=body.incident_id)
    return _out(conversation_or_404(env, cid))


@router.get("/conversations", response_model=Conversations)
def list_(
    env: Env,
    incident: str | None = None,
    q: Annotated[str | None, Query(max_length=100)] = None,
    limit: Annotated[int, Query(ge=1, le=100)] = 30,
    cursor: str | None = None,
) -> Conversations:
    cur_ts, cur_id = decode_cursor(cursor) if cursor else (None, None)
    rows = env.ro("conv_list", incident=incident, q=q or None, cur_ts=cur_ts, cur_id=cur_id, limit=limit)
    nxt = encode_cursor(rows[-1]["updated"], rows[-1]["id"]) if len(rows) == limit else None
    return Conversations(items=[_out(r) for r in rows], next_cursor=nxt)


@router.get("/conversations/{conversation_id}", response_model=ConversationDetail)
def get(conversation_id: str, env: Env) -> ConversationDetail:
    c = conversation_or_404(env, conversation_id)
    msgs = [
        MessageOut(
            id=m["id"],
            role=m["role"],
            text=m["text"],
            ts=iso(m["ts"]),
            path=m["path"] or [],
            tools_used=[ToolUse(**t) for t in json.loads(m["tools"] or "[]")],
            cypher=m["cypher"],
            attachments=m["attachments"] or [],
        )
        for m in env.ro("conv_messages", conv=conversation_id)
    ]
    return ConversationDetail(**_out(c).model_dump(), message_list=msgs)


@router.delete("/conversations/{conversation_id}", status_code=204)
def delete(conversation_id: str, env: Env) -> None:
    conversation_or_404(env, conversation_id)
    env.rw("conv_delete_messages", id=conversation_id)
    env.rw("conv_delete", id=conversation_id)
