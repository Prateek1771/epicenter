"""Incident event bus (LLD §9). Agents publish one event per graph write; `GET /incidents/{id}/stream` serves them.

`EventBus` is the interface; `RedisStreamBus` keeps each incident's events in a Redis Stream in FalkorDB's own Redis
(`events:env:<name>:<incident>`), with a per-incident `seq` from `INCR`. The seq is the SSE `id`: it survives API
restarts, and any replica can replay from it, so a reconnecting client sends `Last-Event-ID` and misses nothing.
"""

import json
import logging
from typing import Protocol

from api.graph import get_graph

log = logging.getLogger("epicenter.events")

EVENTS = {
    "incident.status",
    "hypothesis.created",
    "evidence.added",
    "footprint",
    "hypothesis.status",
    "verdict",
    "no_root_cause",
    "memory.similar",
    "explanation",
    "action",
    "error",
    "receipts",  # once per run: every graph query it made, numbered, with timings (phase 12)
}


class EventBus(Protocol):
    def publish(self, env_key: str, incident_id: str, event: str, data: dict) -> int: ...

    def history(self, env_key: str, incident_id: str, after_seq: int = 0, block_ms: int = 0) -> list[dict]: ...

    def last_seq(self, env_key: str, incident_id: str) -> int: ...


class RedisStreamBus:
    """`env_key` is the env graph key (`env:<name>`), so streams stay per environment like the graphs."""

    def publish(self, env_key: str, incident_id: str, event: str, data: dict) -> int:
        if event not in EVENTS:
            raise ValueError(f"unknown event {event!r}")
        seq = get_graph().publish_event(f"{env_key}:{incident_id}", event, json.dumps(data, default=str))
        log.info(json.dumps({"incident_id": incident_id, "event": event, "seq": seq}))
        return seq

    def history(self, env_key: str, incident_id: str, after_seq: int = 0, block_ms: int = 0) -> list[dict]:
        """Events after `after_seq`, oldest first; with `block_ms`, waits that long for the next ones (live tail)."""
        return get_graph().read_events(f"{env_key}:{incident_id}", after_seq, block_ms)

    def last_seq(self, env_key: str, incident_id: str) -> int:
        return get_graph().last_event_seq(f"{env_key}:{incident_id}")


bus: EventBus = RedisStreamBus()


def publish(env_key: str, incident_id: str, event: str, data: dict) -> int:
    return bus.publish(env_key, incident_id, event, data)
