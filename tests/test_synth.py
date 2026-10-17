"""Synthetic samples (phase 11, EXAMPLE_RUNS §4): same seed → same bytes; small cases give their labelled verdict; a
memory climb that starts hours before the alert is found by the slow-burn pass (LLD §3.2 "Fetch", §12 slow-burn row)."""

import json

import pytest

from api import eval as ev
from api.ingest.rcaeval import replay
from api.search.causal import diagnose

gen = ev.synth_gen()


def test_same_seed_gives_byte_identical_files(tmp_path):
    a = gen.generate("small", "config", 7, tmp_path / "a")
    b = gen.generate("small", "config", 7, tmp_path / "b")
    files = sorted(p.name for p in a.iterdir())
    assert files == sorted(p.name for p in b.iterdir()) and "changes.jsonl" in files
    assert all((a / f).read_bytes() == (b / f).read_bytes() for f in files)


def test_two_needs_an_independent_pair():
    with pytest.raises(SystemExit, match="no fault independent"):
        gen.choose(gen.np.random.default_rng(0), gen.topology(gen.np.random.default_rng([1, 0]), "small"), "two")


@pytest.mark.parametrize("fault", ["cpu", "healthy", "mem"])
def test_small_case_gives_its_label(graph, tmp_path, fault):
    d = gen.generate("small", fault, 1, tmp_path)
    label = json.loads((d / "labels.json").read_text())
    env = graph.env("synth-test")
    env.delete()
    try:
        out = replay(d, "synth-test", graph)
        v = diagnose(graph, "synth-test", out["incident"])
        if fault == "mem":  # only the 6 h fetch sees the climb: the short window starts ~12 min before the alert
            slow = env.ro("incident_anomalies", inc=out["incident"])
            assert any(a["detector"] == "slow_burn" and a["kind"] == "mem" for a in slow)
    finally:
        env.delete()
    assert gen.check(label, v["status"], v["root_cause"], v["second_cause"]), (label, v["root_cause"], v["status"])


def test_synth_cases_are_runs_scenarios_with_their_expect(tmp_path, monkeypatch):
    from api import runs
    from api.config import get_settings

    monkeypatch.setattr(get_settings(), "rcaeval_dir", str(tmp_path))
    cpu, ok = gen.generate("small", "cpu", 1, tmp_path), gen.generate("small", "healthy", 1, tmp_path)
    found = {s.id: s for s in runs.rcaeval_cases()}
    assert found[cpu.name].env == "synthetic" and found[cpu.name].expect == {"target_prefix": "svc-0/"}
    assert found[ok.name].expect == runs.NO_ROOT_CAUSE
    # one day apart: never overlap in env:synthetic
    assert (cpu / "inject_time.txt").read_text() != (ok / "inject_time.txt").read_text()
