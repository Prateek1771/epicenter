"""Pydantic models shared by REST, tools and agents (LLD §4). Grows phase by phase.

The REST models mirror docs/API.md, so `/docs` (OpenAPI) shows the documented shapes. Times are ISO-8601 UTC.
"""

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


def scoped_id(incident_id: str, local: str) -> str:
    """Graph key for per-incident ids (Evidence, Hypothesis, Action): `inc-1` + `E3` → `inc-1:E3` (Q-a)."""
    return f"{incident_id}:{local}"


def local_id(stored: str) -> str:
    """What the API and UI show: `inc-1:E3` → `E3`."""
    return stored.rsplit(":", 1)[-1]


IncidentStatus = Literal["open", "diagnosing", "diagnosed", "no_root_cause", "delivered", "resolved"]
HypothesisStatus = Literal["open", "supported", "refuted", "inconclusive", "confirmed", "pruned"]
FaultKind = Literal["errors", "latency", "cpu", "mem", "saturation", "down"]


# --- alerts and incidents ---


class AlertIn(BaseModel):
    alert_id: str
    env: str | None = None
    symptom: str
    starts_at: datetime
    labels: dict[str, str] = {}
    auto_diagnose: bool = True


class AlertAccepted(BaseModel):
    incident_id: str
    status: IncidentStatus
    joined_existing: bool
    stream: str


class IncidentSummary(BaseModel):
    id: str
    status: IncidentStatus
    symptom: str | None
    root_cause: str | None
    confidence: float | None
    opened_at: datetime | None


class IncidentPage(BaseModel):
    items: list[IncidentSummary]
    next_cursor: str | None


class HypothesisOut(BaseModel):
    id: str
    target: str
    target_type: Literal["Operation", "Change"]
    status: HypothesisStatus
    score: float | None
    hops: int
    onset: datetime | None
    score_parts: dict[str, float | str]  # features, plus `pagerank_impl` (falkordb / networkx)


class HypothesisRef(BaseModel):
    id: str
    target: str
    status: HypothesisStatus
    score: float | None = None


class EvidenceOut(BaseModel):
    id: str
    kind: Literal["propagation", "mechanism", "change", "victim", "pagerank", "footprint", "log", "history"]
    verdict: Literal["supports", "refutes"]
    summary: str
    path: list[str]
    ref: str | None


class FootprintSummary(BaseModel):
    coverage: float
    precision: float
    order: float
    summary: str
    unexplained: list[str]


class Verdict(BaseModel):
    root_cause: HypothesisOut
    confidence: float
    footprint: FootprintSummary | None
    second_root_cause: HypothesisOut | None
    runner_up: HypothesisRef | None
    path: list[str]
    evidence: list[EvidenceOut]


class NoRootCause(BaseModel):
    summary: str
    checked: list[str]
    max_coverage: float


class IncidentOut(BaseModel):
    id: str
    env: str
    status: IncidentStatus
    symptom: str | None
    alert_count: int
    gaps: list[str]
    weights_version: str | None
    run: int | None
    verdict: Verdict | None
    no_root_cause: NoRootCause | None = None
    hypotheses: list[HypothesisRef]
    explanation: dict | None = None  # narrator, phase 7
    similar: list[dict] = []  # historian, phase 7
    actions: list[dict] = []  # responder, phase 7


class Accepted(BaseModel):
    incident_id: str
    status: IncidentStatus


class Prediction(BaseModel):
    op: str
    kind: str
    p: float
    hops: int
    onset_window_s: list[int] | None


class FootprintOut(BaseModel):
    hypothesis_id: str
    target: str
    cause_kind: str
    coverage: float
    precision: float
    order: float
    footprint: float
    predicted: list[Prediction]
    matched: list[str]
    missed: list[str]
    unexplained: list[str]
    summary: str


class ChangeNote(BaseModel):
    service: str
    type: str
    ts: datetime


class NoteIn(BaseModel):
    by: str
    text: str
    change: ChangeNote | None = None


class NoteOut(BaseModel):
    decision_id: str
    change_id: str | None


class ResolveIn(BaseModel):
    by: str
    fixed_by_action: str | None = None
    note: str | None = None


class ResolveOut(BaseModel):
    status: Literal["resolved"]


# --- graph views ---


class GraphNode(BaseModel):
    id: str
    label: str
    props: dict


class GraphEdge(BaseModel):
    model_config = ConfigDict(populate_by_name=True)

    from_: str = Field(alias="from")
    to: str
    type: str
    props: dict


class Subgraph(BaseModel):
    nodes: list[GraphNode]
    edges: list[GraphEdge]


class Affected(BaseModel):
    service: str
    operation: str
    hops: int
    owner: str | None


class BlastRadius(BaseModel):
    service: str
    affected: list[Affected]
    counts: dict[str, int]
    past_incidents: list[str]


class SimulateIn(BaseModel):
    service: str | None = None
    operation: str | None = None
    kind: FaultKind
    save: bool = False

    @model_validator(mode="after")
    def one_target(self):
        if (self.service is None) == (self.operation is None):
            raise ValueError("give exactly one of service or operation")
        return self


class SimulatedOp(BaseModel):
    op: str
    service: str | None
    kind: str
    p: float
    hops: int
    expected_delay_s: int
    owner: str | None


class SimulateOut(BaseModel):
    simulation_id: str | None
    target: str
    kind: str
    rules_version: str
    predicted: list[SimulatedOp]
    counts: dict[str, int]


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    falkordb: str
    falkordb_mcp: str
    openrouter: str
    openconnector: str
    query_ms: dict[str, dict[str, float]]
