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


class ChangeRef(BaseModel):
    id: str
    service: str
    type: str
    ts: datetime
    summary: str | None


class Verdict(BaseModel):
    root_cause: HypothesisOut
    confidence: float
    owner: str | None = None  # team owning the root cause's service
    change: ChangeRef | None = None  # the change the `change` evidence attributes, if any
    found_in_ms: int | None = None  # run start → verdict published
    footprint: FootprintSummary | None
    second_root_cause: HypothesisOut | None
    runner_up: HypothesisRef | None
    path: list[str]
    evidence: list[EvidenceOut]


class NoRootCause(BaseModel):
    summary: str
    checked: list[str]
    max_coverage: float


class ClaimOut(BaseModel):
    section: Literal["what", "where", "why"]
    text: str
    cites: list[str]
    support_p: float | None = None  # Jev Noul P(cited evidence supports the claim)
    status: Literal["verified", "unverified", "template", "llm"] | None = None


class ExplanationOut(BaseModel):
    claims: list[ClaimOut]
    dropped: int
    verified: bool
    source: Literal["llm", "template"]  # template → the UI shows "AI explanation unavailable"
    ai_calls: list[dict]


class SimilarOut(BaseModel):
    incident: str
    score: float
    cause: str | None
    fixes: list[str]


class ActionOut(BaseModel):
    id: str
    name: str
    status: Literal["proposed", "done"]
    rank: int
    chosen_by: Literal["history", "runbook", "demoted"]
    precedent: list[str] = []  # incidents an action with this name resolved (newest first)
    # p: Jev relevance (does the action address the cause the evidence shows?)
    p: float | None
    runbook: str | None


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
    explanation: ExplanationOut | None = None
    similar: list[SimilarOut] = []
    actions: list[ActionOut] = []
    delivery: dict | None = None  # per target, from POST /deliver


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


class DeliverIn(BaseModel):
    targets: list[Literal["slack", "linear"]] = Field(min_length=1)
    slack_channel: str | None = None  # Slack channel id; default SLACK_CHANNEL


class DeliverResult(BaseModel):
    target: Literal["slack", "linear"]
    ok: bool
    url: str | None = None
    error: Literal["UPSTREAM_ERROR"] | None = None
    message: str | None = None


class DeliverOut(BaseModel):
    results: list[DeliverResult]


class Attachment(BaseModel):
    """A text file the user attached (.md, .log, .json, …), read in the browser: context, never a command."""

    name: str = Field(min_length=1, max_length=200)
    text: str = Field(max_length=200_000)


class AskIn(BaseModel):
    question: str = Field(min_length=1, max_length=2000)
    incident_id: str | None = None
    conversation_id: str | None = None  # continue a saved conversation: its last turns go to the model as history
    attachments: list[Attachment] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def _attachments_fit(self) -> "AskIn":
        if sum(len(a.text) for a in self.attachments) > 200_000:
            raise ValueError("attachments: 200 KB of text in total at most")
        return self


class ToolUse(BaseModel):
    tool: str
    args: dict


class AskOut(BaseModel):
    answer: str
    path: list[str]
    tools_used: list[ToolUse]
    cypher: str | None  # set when the answer came from the read-only falkordb-mcp fallback
    conversation_id: str | None = None
    message_id: str | None = None  # the saved answer, when the question belonged to a conversation


class ConversationIn(BaseModel):
    title: str | None = Field(default=None, max_length=120)
    incident_id: str | None = None


class ConversationOut(BaseModel):
    id: str
    title: str
    incident: str | None
    created: datetime
    updated: datetime
    messages: int


class Conversations(BaseModel):
    items: list[ConversationOut]
    next_cursor: str | None = None


class MessageOut(BaseModel):
    id: str
    role: Literal["user", "assistant"]
    text: str
    ts: datetime
    path: list[str] = []
    tools_used: list[ToolUse] = []
    cypher: str | None = None
    attachments: list[str] = []  # names only: the text is never stored


class ConversationDetail(ConversationOut):
    message_list: list[MessageOut]


class GraphEvidence(BaseModel):
    id: str
    kind: str
    verdict: Literal["supports", "refutes"]
    summary: str
    path: list[str]


class GraphHypothesis(BaseModel):
    id: str
    op: str
    status: HypothesisStatus
    score: float | None
    hops: int
    round: int
    evidence: list[GraphEvidence]


class AnomalyMark(BaseModel):
    kind: str
    onset: int | None
    score: float | None


class GraphOp(BaseModel):
    id: str
    service: str
    service_kind: str | None
    anomaly: AnomalyMark | None


class GraphCall(BaseModel):
    src: str
    dst: str
    rps: float | None
    err_rate: float | None
    p95_ms: float | None


class GraphChange(BaseModel):
    id: str
    service: str
    type: str
    ts: int  # epoch s, like anomaly onsets on the canvas
    summary: str | None


class IncidentGraph(BaseModel):
    """Everything the incident canvas draws for the current run; SSE events patch the same shape by id."""

    incident: str
    run: int | None
    status: IncidentStatus
    symptom: str | None
    root_cause: str | None
    second_cause: str | None
    last_seq: int  # open the stream with ?after=last_seq: the snapshot already contains everything before it
    hypotheses: list[GraphHypothesis]
    nodes: list[GraphOp]
    edges: list[GraphCall]
    alert_ts: int | None = None  # epoch s, like anomaly onsets: the canvas's time axis
    changes: list[GraphChange] = []  # on the canvas's services, from lookback before the alert to the window end
    receipts: dict | None = None  # the last run's numbered graph queries (the `receipts` event's payload)


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


class Explore(Subgraph):
    label_counts: dict[str, int]  # every node in the env, by label (the legend)
    truncated: bool


class TopologyNode(BaseModel):
    id: str  # service name, or operation id at level=operation
    service: str
    kind: str | None
    owner: str | None
    ops: int | None = None
    anomalies: list[dict] = []  # [{incident, kind, score}] from unresolved incidents in the window
    root_cause_of: list[str] = []


class TopologyEdge(BaseModel):
    src: str
    dst: str
    rps: float | None
    err_rate: float | None
    p95_ms: float | None


class Topology(BaseModel):
    level: Literal["service", "operation"]
    nodes: list[TopologyNode]
    edges: list[TopologyEdge]
    truncated: bool


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
    sources: list[str] = []  # the failing service's own operations
    edges: list[GraphCall] = []  # CALLS among sources + affected: the graph view


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
    edges: list[GraphCall] = []  # CALLS among the predicted ops: the graph view


class SimCompare(BaseModel):
    incident: str
    observed: int
    coverage: float
    precision: float
    footprint: float
    explains: str
    matched: list[str]
    missed: list[str]
    unexplained: list[str]


class SimCompareOut(BaseModel):
    target: str
    kind: str
    items: list[SimCompare]


class SimulationItem(BaseModel):
    id: str
    target: str
    kind: str
    ts: int
    rules_version: str | None
    operations: int


class Simulations(BaseModel):
    items: list[SimulationItem]


class RuleOut(BaseModel):
    id: str
    cause_kinds: list[str]
    symptom_kind: str
    direction: str
    p: float
    delay_s_max: int
    service_kind: str | None
    caller_kind: str | None
    version: str


class Rules(BaseModel):
    items: list[RuleOut]


class ServiceItem(BaseModel):
    name: str
    kind: str | None
    operations: int


class Services(BaseModel):
    items: list[ServiceItem]


class RunbookOut(BaseModel):
    id: str
    kind: str | None
    steps: list[str]
    success: dict[str, int]  # step → times it fixed an incident


class Runbooks(BaseModel):
    items: list[RunbookOut]


class ServiceRisk(BaseModel):
    name: str
    kind: str | None
    callers: int  # distinct calling services
    incidents: int  # incidents rooted here (current run's root cause)
    owner: str | None


class ServicesRisk(BaseModel):
    items: list[ServiceRisk]


class Envs(BaseModel):
    items: list[str]
    default: str


class EvalScore(BaseModel):
    ac1: float | None
    ac3: float | None = None


class EvalCase(BaseModel):
    case: str
    split: str | None
    service: str  # the labelled root-cause service
    fault: str
    top3: list[str]  # our top-3 services, verdict first; empty = no_root_cause
    hit1: bool
    hit3: bool
    confidence: float | None = None
    diagnose_ms: float | None = None
    variants: dict[str, str | None] = {}  # ablation → its top-1 service
    parts: dict[str, float] = {}  # the verdict's score parts


class EvalRun(BaseModel):
    run: str
    ac1: float | None
    ac3: float | None
    cases: int
    weights_version: str | None


class EvalSummary(BaseModel):
    """GET /eval: the newest `python -m api.eval` result (data/eval), with its N1/N2 timings and one row per case."""

    run: str
    suite: str
    system: str
    cases: int
    ac1: float | None
    ac3: float | None
    by_fault: dict[str, dict[str, float | int | None]]
    split: dict[str, dict[str, float | int | None]]
    ablations: dict[str, EvalScore]
    memory: dict[str, float | int | None]
    weights_version: str | None
    rules_version: str
    n1_ms: dict[str, float | None] | None = None
    n2_p95_ms: dict[str, float] | None = None
    per_case: list[EvalCase] = []
    history: list[EvalRun] = []  # every stored RE2 run, oldest first
    synth: dict | None = None  # the newest synthetic-suite summary (by_size), reported apart


class Health(BaseModel):
    status: Literal["ok", "degraded"]
    falkordb: str
    falkordb_mcp: str
    openrouter: str
    jev: str
    openconnector: str
    query_ms: dict[str, dict[str, float]]


# --- example runs (phase 9) ---


class ScenarioOut(BaseModel):
    env: str
    id: str
    title: str
    expected: str
    kind: Literal["fault", "load", "baseline", "replay"]
    ready: bool  # live: its example environment is up (fault runner health); replay: the case is on disk
    expect: dict[str, str] | None = None  # machine-readable `expected` (runs.matches): target_prefix or status


class Scenarios(BaseModel):
    items: list[ScenarioOut]
    runner: bool  # the host fault runner answered


class RunIn(BaseModel):
    env: str
    scenario: str


class RunAccepted(BaseModel):
    run_id: str
    incident_id: str
    alert_at: datetime  # when the alert fires (fault + settle time); the diagnosis starts then
    change_id: str | None = None


class RunUndone(BaseModel):
    run_id: str
    status: str


class RunOut(BaseModel):
    run_id: str
    env: str
    scenario: str
    title: str
    kind: Literal["fault", "load", "baseline", "replay"]
    status: str  # started · fault_failed · undone
    incident_id: str
    started_at: datetime
    alert_at: datetime
    detail: str | None = None
    verdict: str | None = None  # the root cause, or the incident status when there is none (no_root_cause, diagnosing)
    matches: bool | None = None  # the verdict against the scenario's `expect`; None until there is a verdict


class Runs(BaseModel):
    items: list[RunOut]
