"""flip-commerce fault scenarios (EXAMPLE_RUNS §2.3). The only code that changes this environment (AGENTS rule 9).

    python examples/flip-commerce/faults.py <scenario> [--undo] [--change-id ID]

Every fault journals its change **before** acting (examples/journal.py), so the change is on record with a time that
precedes its effect. Each one is reversible with --undo, which restores exactly what the fault touched (run/faults/).
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import journal  # noqa: E402
import run  # noqa: E402

ENV = "flip-commerce"
STATE = run.RUN / "faults"
# A replica-set name typo in flip-node's MONGO_URI (fk-rss for fk-rs): it can't connect, can't boot, crash-loops.
# Mongo's calls stop too, so Mongo looks down, while the change on record is flip-node's config. Live-tested
# candidates that changed nothing: socketTimeoutMS=3 (the driver kept serving 7-30 ms queries) and w=5 (the code
# hardcodes writeConcern majority, which overrides the URI).
BAD_MONGO_URI = run.MONGO_URI.replace("replicaSet=fk-rs", "replicaSet=fk-rss")
STRESS_RATE = 400  # requests / s at one flip-node worker: past its saturation point


def _save(name: str, d: dict) -> None:
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / f"{name}.json").write_text(json.dumps(d))


def _load(name: str) -> dict:
    f = STATE / f"{name}.json"
    return json.loads(f.read_text()) if f.exists() else {}


def _stop(containers: list[str]) -> str:
    return run.sh("docker", "stop", "-t", "2", *containers)


def _start(containers: list[str]) -> str:
    return run.sh("docker", "start", *containers) if containers else "nothing to start"


def mongo_primary_down(undo: bool, change_id: str | None) -> str:
    if undo:
        out = _start(_load("mongo-primary-down").get("stopped", []))
        run.wait(f"{run.NODE_URL}/ready", timeout_s=60)
        return out
    members = run.mongo_members()
    primary = next((c for c, s in members.items() if s == "PRIMARY"), None)
    if primary is None:
        raise SystemExit(f"no Mongo primary to stop: {members}")
    journal.record(ENV, "mongodb", "datastore", "infra", f"docker stop {primary} (Mongo primary, fk-rs)",
                   "faults.py:mongo-primary-down", change_id)  # fmt: skip
    _save("mongo-primary-down", {"stopped": [primary]})
    return _stop([primary])


def mongo_majority_lost(undo: bool, change_id: str | None) -> str:
    if undo:
        out = _start(_load("mongo-majority-lost").get("stopped", []))
        run.wait(f"{run.NODE_URL}/ready", timeout_s=90)
        return out
    members = run.mongo_members()
    # keep the primary's container, stop the other two: it steps down, nothing can be elected, writes and reads stop
    others = sorted(c for c, s in members.items() if s != "PRIMARY" and s != "down")[:2]
    journal.record(ENV, "mongodb", "datastore", "infra", f"docker stop {' '.join(others)} (2 of 3 Mongo members)",
                   "faults.py:mongo-majority-lost", change_id)  # fmt: skip
    _save("mongo-majority-lost", {"stopped": others})
    return _stop(others)


def redis_down(undo: bool, change_id: str | None) -> str:
    if undo:
        return _start(["fk-redis"])
    journal.record(ENV, "redis", "datastore", "infra", "docker stop fk-redis (session store)",
                   "faults.py:redis-down", change_id)  # fmt: skip
    return _stop(["fk-redis"])


def circuit_misconfig(undo: bool, change_id: str | None) -> str:
    if undo:
        run.start_node()
        return "flip-node restarted with its normal config"
    journal.record(ENV, "flip-node", "app", "config", "deploy flip-node with MONGO_URI replicaSet=fk-rss (typo)",
                   "faults.py:circuit-misconfig", change_id)  # fmt: skip
    run.start_node({"MONGO_URI": BAD_MONGO_URI}, wait_healthy=False)
    return "flip-node restarted with replicaSet=fk-rss: it can't reach Mongo and won't boot"


def cpu_saturation(undo: bool, change_id: str | None) -> str:
    # no change event: the cause is traffic, not something anyone changed
    if undo:
        run.kill("k6-stress")
        return "stress load stopped"
    run.start_load(STRESS_RATE, name="k6-stress", duration="30m")
    return f"stress load started: {STRESS_RATE} req/s on top of the normal load"


SCENARIOS = {
    "mongo-primary-down": mongo_primary_down,
    "mongo-majority-lost": mongo_majority_lost,
    "redis-down": redis_down,
    "circuit-misconfig": circuit_misconfig,
    "cpu-saturation": cpu_saturation,
}


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("scenario", choices=sorted(SCENARIOS))
    p.add_argument("--undo", action="store_true")
    p.add_argument("--change-id", help="the Change id the API already wrote (POST /runs), so both records are one")
    a = p.parse_args()
    print(SCENARIOS[a.scenario](a.undo, a.change_id))
