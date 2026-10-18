"""Example runs (EXAMPLE_RUNS, API.md "Example runs and eval"): the scenario registry and the host fault runner client.

A live scenario is triggered by `examples/<env>/faults.py` on the host, through `examples/fault_runner.py` (ADR 0012):
the API never gets the Docker socket and never touches an environment itself. RCAEval scenarios are the cases found in
`RCAEVAL_DIR`, replayed and diagnosed.
"""

import json
import re
from dataclasses import dataclass
from pathlib import Path

import httpx

from api.config import get_settings

RUNNER_TIMEOUT_S = 150.0  # a scenario that restarts a server waits for it to come back healthy


@dataclass(frozen=True)
class Scenario:
    env: str
    id: str
    title: str
    expected: str  # the verdict EXAMPLE_RUNS expects
    kind: str = "fault"  # fault · load (no Change: the cause is traffic) · baseline (nothing injected) · replay
    symptom: str = ""  # the operation the alert fires on
    settle_s: int = 60  # fault → alert: long enough for the symptoms to show, shorter than the 120 s pre-alert window
    change: dict | None = None  # {service, service_kind, type, summary}: written before the fault, like a deploy
    expect: dict | None = (
        None  # machine-readable `expected`: {"target_prefix": "redis/"} or {"status": "no_root_cause"}
    )


NO_ROOT_CAUSE = {"status": "no_root_cause"}


def matches(expect: dict | None, status: str | None, root_cause: str | None) -> bool | None:
    """Does a verdict match a scenario's `expect`? None when there is nothing to compare (no expect, or no verdict)."""
    if not expect or status in (None, "open", "diagnosing"):
        return None
    if "status" in expect:
        return status == expect["status"]
    return root_cause is not None and root_cause.startswith(expect["target_prefix"])


# env → examples/<dir>
EXAMPLE_DIRS = {"flip-commerce": "flip-commerce", "astronomy-shop": "otel-demo"}
FLIP_PRODUCTS = "nginx/GET /node/products"
FLIP_CART = "nginx/GET /node/cart"
FLIP_ADD_TO_CART = "nginx/POST /node/cart"
DEMO_CHECKOUT = "frontend/POST /api/checkout"  # checked against the demo's Jaeger operations (3.1.0)
DEMO_ADS = "frontend/GET /api/data"  # the frontend route that calls ad/GetAds

LIVE: list[Scenario] = [
    Scenario("flip-commerce", "mongo-primary-down", "Stop the Mongo primary",
             "no_root_cause: the replica set fails over in < 1 s and reads stay up (primaryPreferred)",
             symptom=FLIP_PRODUCTS,
             change={"service": "mongodb", "service_kind": "datastore", "type": "infra",
                     "summary": "docker stop the Mongo primary (fk-rs)"}, expect=NO_ROOT_CAUSE),
    Scenario("flip-commerce", "mongo-majority-lost", "Lose the Mongo majority (2 of 3 down)", "mongodb, kind down",
             symptom=FLIP_ADD_TO_CART,
             change={"service": "mongodb", "service_kind": "datastore", "type": "infra",
                     "summary": "docker stop 2 of 3 Mongo members (fk-rs)"}, expect={"target_prefix": "mongodb/"}),
    Scenario("flip-commerce", "redis-down", "Stop Redis (sessions)", "redis, kind down", symptom=FLIP_CART,
             change={"service": "redis", "service_kind": "datastore", "type": "infra",
                     "summary": "docker stop the Redis session store"}, expect={"target_prefix": "redis/"}),
    Scenario("flip-commerce", "circuit-misconfig", "Config typo: flip-node can't find its replica set",
             "flip-node/*, change: config (Mongo looks down too, but it's healthy)", symptom=FLIP_PRODUCTS,
             change={"service": "flip-node", "service_kind": "app", "type": "config",
                     "summary": "deploy flip-node with MONGO_URI replicaSet=fk-rss (typo)"},
             expect={"target_prefix": "flip-node/"}),
    Scenario("flip-commerce", "cpu-saturation", "Overload one flip-node worker", "flip-node/*, kind saturation",
             kind="load", symptom=FLIP_PRODUCTS, expect={"target_prefix": "flip-node/"}),
    Scenario("flip-commerce", "healthy-baseline", "Healthy baseline (no fault)", "no_root_cause", kind="baseline",
             symptom=FLIP_PRODUCTS, settle_s=30, expect=NO_ROOT_CAUSE),
    # OTel Demo (EXAMPLE_RUNS §1): flagd flags; the alert fires on the frontend, the loudest symptom
    Scenario("astronomy-shop", "paymentFailure", "flagd: payment fails 50% of charges",
             "payment/*, change: flag paymentFailure on", symptom=DEMO_CHECKOUT, settle_s=90,  # ~4 checkouts / min
             change={"service": "payment", "service_kind": "app", "type": "flag",
                     "summary": "flag paymentFailure → 50%"}, expect={"target_prefix": "payment/"}),
    Scenario("astronomy-shop", "adHighCpu", "flagd: high CPU in the ad service", "ad/*, kind cpu / latency",
             symptom=DEMO_ADS,
             change={"service": "ad", "service_kind": "app", "type": "flag", "summary": "flag adHighCpu → on"},
             expect={"target_prefix": "ad/"}),
    Scenario("astronomy-shop", "emailMemoryLeak", "flagd: memory leak in the email service",
             "no_root_cause at demo traffic: the leak grows ~10% in 90 s (one per order email), under the detector",
             symptom=DEMO_CHECKOUT, settle_s=90,
             change={"service": "email", "service_kind": "app", "type": "flag",
                     "summary": "flag emailMemoryLeak → 100x"}, expect=NO_ROOT_CAUSE),
]  # fmt: skip

_CASE = re.compile(r"^re2(?P<sys>tt|ob)_(?P<svc>.+)_(?P<fault>cpu|mem|disk|delay|loss|socket)_(?P<n>\d+)$")
_SYSTEM_ENV = {"tt": "rcaeval-tt", "ob": "rcaeval-ob"}
_SYNTH = re.compile(r"^synth-(?P<size>small|medium|huge)_(?P<svc>.+)_(?P<fault>[a-z-]+)_(?P<n>\d+)$")


def _roots() -> list[Path]:
    s = get_settings()
    return [Path(s.rcaeval_dir), Path(s.samples_dir)]  # downloaded or regenerated first, then the committed samples


def case_dir(case: str) -> Path | None:
    """Where a replay case lives: RCAEVAL_DIR (downloads, local regenerations) or the committed examples/samples."""
    return next((r / case for r in _roots() if (r / case / "inject_time.txt").exists()), None)


def _case_dirs(pattern: str) -> list[Path]:
    seen: dict[str, Path] = {}
    for root in _roots():
        for d in sorted(root.glob(pattern)) if root.exists() else []:
            seen.setdefault(d.name, d)
    return [seen[k] for k in sorted(seen)]


def rcaeval_cases() -> list[Scenario]:
    out = []
    for d in _case_dirs("re2*"):
        m = _CASE.match(d.name)
        if m and (d / "inject_time.txt").exists():
            out.append(Scenario(_SYSTEM_ENV[m["sys"]], d.name, f"RCAEval replay: {m['svc']} {m['fault']} #{m['n']}",
                                f"{m['svc']}/*, kind {m['fault']}", kind="replay",
                                expect={"target_prefix": f"{m['svc']}/"}))  # fmt: skip
    order = {"small": 0, "medium": 1, "huge": 2}  # the demo starts small
    for d in sorted(_case_dirs("synth-*"), key=lambda d: (order.get(d.name[6:].split("_", 1)[0], 3), d.name)):
        if (m := _SYNTH.match(d.name)) and (d / "labels.json").exists():
            healthy = json.loads((d / "labels.json").read_text(encoding="utf-8"))["status"] == "no_root_cause"
            out.append(Scenario("synthetic", d.name, f"Synthetic {m['size']}: {m['fault']} on {m['svc']}",
                                "no_root_cause" if healthy else f"{m['svc']}/*", kind="replay",
                                expect=NO_ROOT_CAUSE if healthy else {"target_prefix": f"{m['svc']}/"}))  # fmt: skip
    return out


def scenarios() -> list[Scenario]:
    return LIVE + rcaeval_cases()


def find(env: str, scenario_id: str) -> Scenario | None:
    return next((s for s in scenarios() if s.env == env and s.id == scenario_id), None)


class RunnerError(Exception):
    pass


class Runner:
    """Client for `examples/fault_runner.py`. Every call carries the shared token (`FAULT_RUNNER_TOKEN`)."""

    def __init__(self, client: httpx.Client | None = None):
        s = get_settings()
        self.url = s.fault_runner_url.rstrip("/")
        self.token = s.fault_runner_token or ""
        self.client = client or httpx.Client()

    def health(self) -> dict[str, bool]:
        """env → its example environment is up. Empty when the runner can't be reached."""
        try:
            r = self.client.get(f"{self.url}/health", headers={"X-Runner-Token": self.token}, timeout=8.0)
            r.raise_for_status()
            return {k: bool(v) for k, v in r.json().get("envs", {}).items()}
        except (httpx.HTTPError, ValueError):
            return {}

    def fault(self, env: str, scenario: str, undo: bool = False, change_id: str | None = None) -> str:
        body = {"env": env, "scenario": scenario, "undo": undo, "change_id": change_id}
        try:
            r = self.client.post(f"{self.url}/fault", json=body, headers={"X-Runner-Token": self.token},
                                 timeout=RUNNER_TIMEOUT_S)  # fmt: skip
        except httpx.HTTPError as e:
            raise RunnerError(f"fault runner unreachable: {e}") from e
        d = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
        if r.status_code != 200 or not d.get("ok"):
            raise RunnerError(d.get("output") or f"fault runner answered {r.status_code}")
        return str(d.get("output", ""))
