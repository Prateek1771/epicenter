"""Startup seed: indexes, owners, runbooks (per env graph) and propagation rules (kb:propagation).

Every statement is idempotent: MERGE for data, and "already indexed" errors are ignored for indexes.
"""

import json
import logging
from pathlib import Path

import yaml

from api.graph import EnvGraph, Graph

log = logging.getLogger("epicenter.seed")

SEED_DIR = Path(__file__).resolve().parents[2] / "seed"
ENV_INDEXES = [
    "idx_service",
    "idx_operation",
    "idx_anomaly",
    "idx_change",
    "idx_incident",
    "idx_hypothesis",
    "idx_person",
    "idx_simulation",
    "idx_signal",
    "idx_signal_text",
    "idx_incident_signature",
]


def _create_index(g: EnvGraph, qid: str) -> None:
    try:
        g.rw(qid)
    except Exception as e:
        if "already indexed" not in str(e):
            raise


def seed_indexes(g: EnvGraph) -> None:
    for qid in ENV_INDEXES:
        _create_index(g, qid)


def _env_section(path: Path, env_name: str) -> dict:
    return (yaml.safe_load(path.read_text(encoding="utf-8")) or {}).get(env_name) or {}


def seed_owners(g: EnvGraph, env_name: str, path: Path = SEED_DIR / "owners.yaml") -> None:
    for team in _env_section(path, env_name).get("teams", []):
        g.rw("seed_team", team=team["name"], services=sorted(team.get("services", [])))
        for m in team.get("members", []):
            g.rw("seed_member", team=team["name"], handle=m["handle"], name=m.get("name", m["handle"]))


def seed_runbooks(g: EnvGraph, env_name: str, path: Path = SEED_DIR / "runbooks.yaml") -> None:
    for rb in _env_section(path, env_name).get("runbooks", []):
        g.rw("seed_runbook", id=rb["id"], kind=rb["kind"], steps=rb["steps"], services=sorted(rb.get("services", [])))


def rule_id(rule: dict) -> str:
    """Stable id from the rule's content: `errors+down->errors:upstream`, plus `@datastore` when restricted."""
    rid = f"{'+'.join(rule['cause'])}->{rule['symptom']}:{rule['direction']}"
    return f"{rid}@{rule['kind_of_service']}" if rule.get("kind_of_service") else rid


def seed_rules(kb: EnvGraph, path: Path = SEED_DIR / "propagation_rules.yaml") -> None:
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    version = str(doc["version"])
    stored = [r["version"] for r in kb.ro("rules_version")]
    if stored and stored != [version]:
        log.info(json.dumps({"event": "rules_replaced", "from": stored, "to": version}))
        kb.delete()  # GRAPH_SCHEMA §7: kb is replaced as a whole when the rules version changes
    _create_index(kb, "idx_rule")
    for rule in doc["rules"]:
        kb.rw(
            "seed_rule",
            id=rule_id(rule),
            cause=rule["cause"],
            symptom=rule["symptom"],
            direction=rule["direction"],
            p=rule["p"],
            delay_s_max=rule["delay_s_max"],
            kind_of_service=rule.get("kind_of_service"),
            version=version,
        )


def seed_all(graph: Graph, env_name: str) -> None:
    env = graph.env(env_name)
    seed_indexes(env)
    seed_owners(env, env_name)
    seed_runbooks(env, env_name)
    seed_rules(graph.kb())
    log.info(json.dumps({"event": "seeded", "env": env_name}))
