"""Test-run reports (phase 12): findings.md + agent-context.md, numbered, with what a coding agent needs per failure."""

from datetime import UTC, datetime

from tests import report

META = {"started": "2026-10-16T10:00:00+00:00", "duration_s": 12.5, "exitstatus": 1, "args": "tests/test_simulate.py",
        "git": "abc1234", "dirty": 2, "falkordb_tag": "v4.22.1", "weights": "2026-10-16.v3"}  # fmt: skip
RESULTS = [
    {"nodeid": "tests/test_simulate.py::test_ok", "outcome": "passed", "when": "call", "duration": 0.4,
     "file": "tests/test_simulate.py", "line": 10, "message": ""},
    {"nodeid": "tests/test_simulate.py::test_footprint", "outcome": "failed", "when": "call", "duration": 1.2,
     "file": "tests/test_simulate.py", "line": 42, "message": "assert 0.5 == 0.75"},
    {"nodeid": "tests/test_smoke.py::test_falkordb_features", "outcome": "skipped", "when": "setup", "duration": 0.0,
     "file": "tests/test_smoke.py", "line": 4, "message": "FalkorDB not reachable"},
]  # fmt: skip


def test_reports_are_numbered_and_never_overwritten(tmp_path):
    a = report.write(tmp_path, RESULTS, META)
    b = report.write(tmp_path, RESULTS, META)
    assert a.name.startswith("0001-") and b.name.startswith("0002-") and a != b
    assert {p.name for p in a.iterdir()} == {"findings.md", "agent-context.md"}
    assert report.next_dir(tmp_path, datetime(2026, 1, 1, tzinfo=UTC)).name == "0003-20260101T000000Z"


def test_findings_list_totals_failures_and_skips():
    md = report.render_findings(RESULTS, META)
    assert md.startswith("# Test findings: 1 failed")
    assert "1 passed · 1 failed · 1 skipped" in md and "2 uncommitted" in md
    assert "`tests/test_simulate.py:42`" in md and "assert 0.5 == 0.75" in md
    assert "FalkorDB not reachable" in md


def test_agent_context_points_each_failure_at_code_spec_and_rerun():
    md = report.render_agent_context(RESULTS, META)
    assert "### 1. `tests/test_simulate.py::test_footprint`" in md
    assert 'pytest "tests/test_simulate.py::test_footprint" -q --no-report' in md
    assert "docs/LLD.md §7 (Fault Simulator)" in md
    assert "`api/search/simulate.py`" in md  # from the test file's own imports
    assert "Only `api/graph.py` talks to FalkorDB" in md and "down -v" in md
    assert "Nothing failed" in report.render_agent_context(RESULTS[:1], META)


def test_modules_under_test_resolve_package_imports():
    mods = report.modules_under_test(report.ROOT / "tests" / "test_flow.py")
    assert "api/agents/flow.py" in mods and "api/search/causal.py" in mods
    assert all((report.ROOT / m).exists() for m in mods)
