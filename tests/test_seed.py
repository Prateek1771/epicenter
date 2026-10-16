from pathlib import Path

from api.ingest.seed import ENV_INDEXES, rule_id, seed_indexes, seed_owners, seed_rules, seed_runbooks

SEED = Path(__file__).resolve().parents[1] / "seed"


def _seed_env(g):
    seed_indexes(g)
    seed_owners(g, "flip-commerce")
    seed_runbooks(g, "flip-commerce")


def test_env_seed_is_idempotent(blank):
    _seed_env(blank)
    nodes, indexes = blank.ro("count_nodes"), blank.ro("list_indexes")
    _seed_env(blank)
    assert blank.ro("count_nodes") == nodes
    assert blank.ro("list_indexes") == indexes
    labels = {r["label"] for r in indexes}
    assert {"Service", "Operation", "Anomaly", "Incident", "Signal"} <= labels
    assert len(ENV_INDEXES) == 11


def test_owners_are_per_env(blank):
    seed_owners(blank, "flip-commerce")
    seed_owners(blank, "no-such-env")  # unknown env: nothing written
    rows = blank.ro("who_knows", svc="mongodb")
    assert [r["handle"] for r in rows] == ["data-oncall"]


def test_rules_seed_and_version_replace(blank, tmp_path):
    seed_rules(blank)
    seed_rules(blank)
    [v] = blank.ro("rules_version")
    assert v["version"] == "2026-10-15"
    count = blank.ro("count_nodes")[0]["n"]
    assert count == 7

    bumped = tmp_path / "rules.yaml"
    text = (SEED / "propagation_rules.yaml").read_text(encoding="utf-8")
    rules = [ln for ln in text.splitlines() if ln.strip().startswith("- {")]
    bumped.write_text("version: 2026-11-01\nrules:\n" + rules[0] + "\n", encoding="utf-8")
    seed_rules(blank, bumped)
    assert blank.ro("rules_version") == [{"version": "2026-11-01"}]
    assert blank.ro("count_nodes") == [{"n": 1}]  # old version replaced as a whole


def test_rule_ids_are_stable():
    rule = {"cause": ["down"], "symptom": "errors", "direction": "upstream", "kind_of_service": "datastore"}
    assert rule_id(rule) == "down->errors:upstream@datastore"
