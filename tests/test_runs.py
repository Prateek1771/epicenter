"""Example runs API (api/routes/runs.py): scenarios, a live run with a fake fault runner, undo, an RCAEval replay."""

from pathlib import Path

import pytest

from api import eval as suite
from api import runs
from api.config import get_settings
from tests.conftest import API_ENV
from tests.test_rcaeval import case_dir  # noqa: F401  (fixture: a synthetic RCAEval case)

SC = runs.Scenario(API_ENV, "db-down", "Stop the db", "payment, change: docker stop", symptom="frontend/GET /checkout",
                   settle_s=0, change={"service": "payment", "service_kind": "app", "type": "infra",
                                       "summary": "docker stop payment"})  # fmt: skip


class FakeRunner:
    def __init__(self, client, up=True, fail=False):
        self.client, self.up, self.fail = client, up, fail
        self.calls: list[tuple] = []

    def health(self):
        return {API_ENV: True} if self.up else {}

    def fault(self, env, scenario, undo=False, change_id=None):
        # what the graph holds at the moment the fault fires: the change must already be on record
        recorded = [c["id"] for c in self.client.g.ro("recent_changes", svc="payment", since=0)]
        self.calls.append((env, scenario, undo, change_id, recorded))
        if self.fail:
            raise runs.RunnerError("docker: no such container")
        return "stopped payment"


@pytest.fixture
def live(client, monkeypatch):
    monkeypatch.setattr(runs, "LIVE", [SC])
    client.app.state.runner = FakeRunner(client)
    return client


def test_scenarios_list_live_and_replay_with_readiness(live, monkeypatch, tmp_path):
    (tmp_path / "re2tt_ts-auth-service_cpu_1").mkdir()
    (tmp_path / "re2tt_ts-auth-service_cpu_1" / "inject_time.txt").write_text("1")
    monkeypatch.setattr(get_settings(), "rcaeval_dir", str(tmp_path))
    monkeypatch.setattr(get_settings(), "samples_dir", str(tmp_path / "no-samples"))
    d = live.get("/api/v1/runs/scenarios").json()
    assert d["runner"] is True
    assert [(i["env"], i["id"], i["kind"], i["ready"]) for i in d["items"]] == [
        (API_ENV, "db-down", "fault", True),
        ("rcaeval-tt", "re2tt_ts-auth-service_cpu_1", "replay", True),
    ]
    live.app.state.runner.up = False
    assert live.get("/api/v1/runs/scenarios").json()["items"][0]["ready"] is False


def test_live_run_writes_the_change_before_the_fault_then_diagnoses(live):
    r = live.post("/api/v1/runs", json={"env": API_ENV, "scenario": "db-down"})
    assert r.status_code == 202, r.text
    run = r.json()
    [(env, scenario, undo, change_id, recorded)] = live.app.state.runner.calls
    assert (env, scenario, undo) == (API_ENV, "db-down", False)
    assert change_id == run["change_id"] and change_id in recorded  # on record before the fault fired
    inc = live.get(f"/api/v1/incidents/{run['incident_id']}", params={"env": API_ENV}).json()
    assert inc["symptom"] == "frontend/GET /checkout"
    assert inc["status"] in ("diagnosed", "no_root_cause")  # the background diagnosis ran (settle 0)
    assert live.g.ro("run_get", id=run["run_id"])[0]["status"] == "started"


def test_back_to_back_runs_get_their_own_incidents(live, monkeypatch):
    # the alert join window folds a storm into one incident; a scripted run is its own fault
    ids = []
    for ts in (1_800_000_000, 1_800_000_060):
        monkeypatch.setattr("api.routes.runs.time.time", lambda ts=ts: ts)
        ids.append(live.post("/api/v1/runs", json={"env": API_ENV, "scenario": "db-down"}).json()["incident_id"])
    assert ids == ["inc-run-1800000000", "inc-run-1800000060"]


def test_recent_runs_are_the_shared_record(live):
    run = live.post("/api/v1/runs", json={"env": API_ENV, "scenario": "db-down"}).json()
    live.delete(f"/api/v1/runs/{run['run_id']}", params={"env": API_ENV})
    [r] = live.get("/api/v1/runs", params={"env": API_ENV}).json()["items"]
    assert (r["run_id"], r["status"], r["incident_id"], r["title"]) == (run["run_id"], "undone", run["incident_id"],
                                                                      "Stop the db")  # fmt: skip
    assert live.get("/api/v1/runs", params={"env": "no-such-env"}).json() == {"items": []}


def test_undo_calls_the_runner_once(live):
    run = live.post("/api/v1/runs", json={"env": API_ENV, "scenario": "db-down"}).json()
    for _ in range(2):
        r = live.delete(f"/api/v1/runs/{run['run_id']}", params={"env": API_ENV})
        assert r.json() == {"run_id": run["run_id"], "status": "undone"}
    assert [c[2] for c in live.app.state.runner.calls] == [False, True]


def test_env_down_and_fault_failure_are_coded_errors(live):
    live.app.state.runner.up = False
    r = live.post("/api/v1/runs", json={"env": API_ENV, "scenario": "db-down"})
    assert (r.status_code, r.json()["error"]["code"]) == (503, "ENV_NOT_RUNNING")
    live.app.state.runner.up, live.app.state.runner.fail = True, True
    r = live.post("/api/v1/runs", json={"env": API_ENV, "scenario": "db-down"})
    assert (r.status_code, r.json()["error"]["code"]) == (502, "FAULT_FAILED")
    r = live.post("/api/v1/runs", json={"env": API_ENV, "scenario": "nope"})
    assert (r.status_code, r.json()["error"]["code"]) == (404, "SCENARIO_NOT_FOUND")


def test_replay_scenario_ingests_and_diagnoses(client, monkeypatch, case_dir):  # noqa: F811
    monkeypatch.setattr(get_settings(), "rcaeval_dir", str(case_dir.parent))
    env = "test-runs-rc"
    monkeypatch.setattr(runs, "_SYSTEM_ENV", {"tt": env, "ob": env})
    try:
        r = client.post("/api/v1/runs", json={"env": env, "scenario": case_dir.name})
        assert r.status_code == 202, r.text
        inc = client.get(f"/api/v1/incidents/{r.json()['incident_id']}", params={"env": env}).json()
        assert inc["verdict"]["root_cause"]["target"].startswith("db/")  # the synthetic case's slow database
        [run] = client.get("/api/v1/runs", params={"env": env}).json()["items"]
        # the card's badge: the case is named after `back` (its expect), the slow op is db, so it says "differs"
        assert run["verdict"].startswith("db/") and run["matches"] is False
    finally:
        client.app.state.graph.env(env).delete()


def test_every_scenario_has_a_machine_readable_expect_and_matches_reads_it():
    from api.runs import LIVE, NO_ROOT_CAUSE, matches

    assert all(s.expect for s in LIVE)  # syscheck and the /runs card compare against it
    assert matches({"target_prefix": "redis/"}, "diagnosed", "redis/GET") is True
    assert matches({"target_prefix": "redis/"}, "diagnosed", "redisx/GET") is False
    assert matches({"target_prefix": "redis/"}, "no_root_cause", None) is False
    assert matches(NO_ROOT_CAUSE, "no_root_cause", None) is True
    assert matches(NO_ROOT_CAUSE, "diagnosed", "redis/GET") is False
    assert matches(NO_ROOT_CAUSE, "diagnosing", None) is None and matches(None, "diagnosed", "x/y") is None


def test_committed_samples_are_listed_and_replayable(monkeypatch, tmp_path):
    """A fresh clone has no data/: the committed examples/samples give Demo 1 every fault at every size."""
    monkeypatch.setattr(get_settings(), "rcaeval_dir", str(tmp_path / "empty"))
    synth = [s for s in runs.rcaeval_cases() if s.env == "synthetic"]
    sizes = [s.id.split("_", 1)[0] for s in synth]
    assert (sizes.count("synth-small"), sizes.count("synth-medium"), sizes.count("synth-huge")) == (8, 9, 9)
    assert sizes == sorted(sizes, key=["synth-small", "synth-medium", "synth-huge"].index)  # the demo starts small
    for s in synth:
        d = runs.case_dir(s.id)
        assert d is not None and all((d / f).exists() for f in ("labels.json", "traces.parquet", "metrics.parquet",
                                                                 "logs.parquet", "inject_time.txt"))  # fmt: skip
    assert runs.case_dir("synth-small_nope_cpu_1") is None


def test_committed_samples_match_the_generator(tmp_path):
    """The committed samples are exactly what examples/synthetic/gen.py writes for seed 1 (no drift)."""
    gen = suite.synth_gen()
    for size, fault in (("small", "loud-victim"), ("medium", "config")):
        made = gen.generate(size, fault, 1, tmp_path)
        committed = Path(get_settings().samples_dir) / made.name
        assert sorted(f.name for f in made.iterdir()) == sorted(f.name for f in committed.iterdir())
        assert all((made / f.name).read_bytes() == f.read_bytes() for f in committed.iterdir()), made.name
