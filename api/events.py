"""Incident event bus (LLD §9). Agents publish one event per graph write; phase 6 streams them over SSE.

`EventBus` is the interface; `InProcessBus` is the one implementation.
ponytail: in-process, so it holds for one API process. With more replicas, put Redis Streams (FalkorDB already runs
Redis) behind the same interface; `seq` stays the per-incident ordering key a reconnecting client resumes from.
"""

import json
import logging
import threading
from collections import defaultdict, deque
from typing import Protocol

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
}


class EventBus(Protocol):
    def publish(self, incident_id: str, event: str, data: dict) -> int: ...

    def history(self, incident_id: str, after_seq: int = 0) -> list[dict]: ...


class InProcessBus:
    """Per-incident monotonically increasing `seq` and a bounded history for replay after a reconnect."""

    def __init__(self, keep: int = 5000):
        self._lock = threading.Lock()  # investigators publish from worker threads
        self._seq: dict[str, int] = defaultdict(int)
        self._history: dict[str, deque] = defaultdict(lambda: deque(maxlen=keep))

    def publish(self, incident_id: str, event: str, data: dict) -> int:
        if event not in EVENTS:
            raise ValueError(f"unknown event {event!r}")
        with self._lock:
            self._seq[incident_id] += 1
            seq = self._seq[incident_id]
            self._history[incident_id].append({"seq": seq, "event": event, "data": data})
        log.info(json.dumps({"incident_id": incident_id, "event": event, "seq": seq}))
        return seq

    def history(self, incident_id: str, after_seq: int = 0) -> list[dict]:
        with self._lock:
            return [e for e in self._history[incident_id] if e["seq"] > after_seq]


bus: EventBus = InProcessBus()


def publish(incident_id: str, event: str, data: dict) -> int:
    return bus.publish(incident_id, event, data)
