"""Shared pieces of the REST routes: env binding, coded errors, time and cursor helpers."""

import base64
import binascii
import json
from datetime import UTC, datetime
from typing import Annotated

from fastapi import Depends, Query, Request

from api.config import get_settings
from api.graph import EnvGraph, Graph


class ApiError(Exception):
    """A coded error from docs/API.md#errors; main.py renders it in the error envelope."""

    def __init__(self, status: int, code: str, message: str):
        super().__init__(message)
        self.status, self.code, self.message = status, code, message


def graph(request: Request) -> Graph:
    return request.app.state.graph


def env_graph(request: Request, env: Annotated[str | None, Query()] = None) -> EnvGraph:
    """`?env=<name>` (default ENV_NAME) → that env's graph; 404 ENV_NOT_FOUND if it has none."""
    return resolve_env(request, env)


def resolve_env(request: Request, name: str | None) -> EnvGraph:
    name = name or get_settings().env_name
    g = graph(request)
    if name not in g.env_names():
        raise ApiError(404, "ENV_NOT_FOUND", f"No environment {name!r}")
    return g.env(name)


Env = Annotated[EnvGraph, Depends(env_graph)]


def env_name(env: EnvGraph) -> str:
    return env.key.removeprefix("env:")


def incident_or_404(env: EnvGraph, incident_id: str) -> dict:
    rows = env.ro("incident", inc=incident_id)
    if not rows:
        raise ApiError(404, "INCIDENT_NOT_FOUND", f"No incident {incident_id!r} in env {env_name(env)!r}")
    return rows[0]


def iso(ts: int | float | None) -> datetime | None:
    """The graph keeps epoch seconds; the API speaks ISO-8601 UTC."""
    return None if ts is None else datetime.fromtimestamp(ts, UTC)


def epoch(dt: datetime) -> int:
    return int((dt if dt.tzinfo else dt.replace(tzinfo=UTC)).timestamp())


def encode_cursor(opened_at: int, incident_id: str) -> str:
    return base64.urlsafe_b64encode(json.dumps([opened_at, incident_id]).encode()).decode()


def decode_cursor(cursor: str) -> tuple[int, str]:
    try:
        ts, inc = json.loads(base64.urlsafe_b64decode(cursor.encode()))
        return int(ts), str(inc)
    except (ValueError, TypeError, binascii.Error) as e:
        raise ApiError(400, "VALIDATION_ERROR", "Bad cursor") from e
