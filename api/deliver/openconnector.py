"""OpenConnector runtime client (oomol-lab/open-connector): `POST /v1/actions/{id}` with `{input}`.

LLD §10: 10 s timeout, no retries (the user retries from the UI). The `Idempotency-Key` is the caller's scope
(env, incident, run, target) plus a hash of the action and its payload: a retry of the same message after a lost
response never posts twice, and a different message (another env or incident with a reused id, a changed card) never
collides with an old key (OpenConnector answers 409 when one key is reused for a different request).
"""

import hashlib
import json

import httpx

from api.config import get_settings

TIMEOUT_S = 10.0
_transport: httpx.BaseTransport | None = None  # tests swap in an httpx.MockTransport


class UpstreamError(Exception):
    pass


def idempotency_key(scope: str, action_id: str, payload: dict) -> str:
    digest = hashlib.sha256(json.dumps([action_id, payload], sort_keys=True).encode()).hexdigest()[:16]
    return f"{scope}:{digest}"


def run_action(action_id: str, payload: dict, scope: str) -> dict:
    """Run one connector action; returns its `data`. Raises UpstreamError on any failure."""
    s = get_settings()
    if not s.openconnector_url:
        raise UpstreamError("OPENCONNECTOR_URL not set")
    headers = {"Idempotency-Key": idempotency_key(scope, action_id, payload)}
    if s.openconnector_api_key:
        headers["Authorization"] = f"Bearer {s.openconnector_api_key}"
    try:
        with httpx.Client(transport=_transport, timeout=TIMEOUT_S) as c:
            r = c.post(f"{s.openconnector_url.rstrip('/')}/v1/actions/{action_id}", json={"input": payload},
                       headers=headers)  # fmt: skip
        body = r.json()
    except (httpx.HTTPError, ValueError) as e:
        raise UpstreamError(f"{action_id}: {e}") from e
    if r.status_code >= 400 or not body.get("success"):
        raise UpstreamError(f"{action_id}: {r.status_code} {body.get('message') or body.get('error') or body}")
    return body.get("data") or {}
