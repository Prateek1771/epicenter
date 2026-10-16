"""Pydantic models shared by REST, tools and agents (LLD §4). Grows phase by phase."""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel


def scoped_id(incident_id: str, local: str) -> str:
    """Graph key for per-incident ids (Evidence, Hypothesis, Action): `inc-1` + `E3` → `inc-1:E3` (Q-a)."""
    return f"{incident_id}:{local}"


def local_id(stored: str) -> str:
    """What the API and UI show: `inc-1:E3` → `E3`."""
    return stored.rsplit(":", 1)[-1]


class HypothesisOut(BaseModel):
    id: str
    target: str
    target_type: Literal["Operation", "Change"]
    status: Literal["open", "supported", "refuted", "inconclusive", "confirmed", "pruned"]
    score: float | None
    score_parts: dict[str, float]
    hops: int
    onset: datetime | None


class EvidenceOut(BaseModel):
    id: str
    kind: Literal["propagation", "mechanism", "change", "victim", "pagerank", "footprint", "log", "history"]
    verdict: Literal["supports", "refutes"]
    summary: str
    path: list[str]
    ref: str | None


class Verdict(BaseModel):
    incident_id: str
    root_cause: HypothesisOut
    confidence: float
    runner_up: HypothesisOut | None
    path: list[str]
    evidence: list[EvidenceOut]
