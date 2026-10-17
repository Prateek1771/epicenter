"""Test-run reports (phase 12): every pytest session writes two Markdown files into `data/reports/<n>-<utc>/`.

    findings.md       what ran, what passed and failed, timings: for people
    agent-context.md  a guide any coding agent (Claude Code, Codex, Cursor, …) can be pointed at to understand the
                      results and fix what failed without breaking the hard rules

Runs are numbered and never overwritten (history is kept); `data/` is git-ignored. `pytest --no-report` skips it.
`web/scripts/test.mjs` appends the web unit tests to the newest report.
"""

import ast
import json
import os
import re
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
REPORTS = ROOT / "data" / "reports"

# test file → where its behaviour is specified, so a fix starts from the design and not from the test
SPEC = {
    "test_graph": "docs/LLD.md §2 (graph.py, QUERIES)",
    "test_smoke": "docs/LLD.md §12 (smoke), README §5",
    "test_seed": "docs/LLD.md §2.1, docs/GRAPH_SCHEMA.md §5",
    "test_detect": "docs/LLD.md §3.2 (detectors)",
    "test_rcaeval": "docs/LLD.md §3.1, docs/EXAMPLE_RUNS.md §3",
    "test_spans": "docs/LLD.md §3.1 (spans, otel adapter)",
    "test_otel_adapter": "docs/LLD.md §3.1, docs/EXAMPLE_RUNS.md §1–2",
    "test_causal": "docs/LLD.md §2.2, §6 (search + scoring)",
    "test_score": "docs/LLD.md §6 (scoring, weights.json)",
    "test_simulate": "docs/LLD.md §7 (Fault Simulator)",
    "test_signature": "docs/LLD.md §6, ADR 0008",
    "test_memory": "docs/LLD.md §5.3 (historian), Q5",
    "test_flow": "docs/LLD.md §5 (agents), §9 (events)",
    "test_tools": "docs/LLD.md §2.3, ADR 0003",
    "test_mcp": "ADR 0003, docs/API.md",
    "test_api": "docs/API.md",
    "test_health": "docs/API.md (health), docs/HLD.md §7",
    "test_ask": "docs/LLD.md §5.3 (ask agent)",
    "test_deliver": "docs/LLD.md §5.3 (responder), docs/API.md deliver",
    "test_narrator_contract": "docs/LLD.md §5.3 (narrator contract)",
    "test_calibrate": "docs/phases/phase-07-memory-llm-delivery.md",
    "test_prompt_evals": "api/agents/prompts/",
    "test_runs": "docs/API.md (runs), ADR 0012",
    "test_eval": "docs/phases/phase-10-eval-demo.md, docs/LLD.md §12 (eval)",
    "test_report": "tests/report.py",
}

RULES = [
    "Dependency direction `agents → tools → search → graph`, `ingest → graph`; nothing imports `agents` but `main.py`.",
    "Only `api/graph.py` talks to FalkorDB: add a `QUERIES` entry, never Cypher text elsewhere.",
    "Parameterized Cypher only (`$param`), never f-strings into a query.",
    "The LLM never ranks, never writes topology, never sets hypothesis status.",
    "Determinism: same input → same ranking and `score_parts`. Sort by key, tie-break on id, no `random`, no `hash()`.",
    "No raw telemetry in the graph; one graph per environment; scratch graphs deleted in `finally`.",
    "Read-only towards monitored systems; only `examples/*/faults.py` changes an environment.",
    "Never modify the flip-commerce source repo (`system-design-journey`).",
    "No secrets in the graph, logs or git.",
]

DONT = [
    "`docker compose down -v` or `GRAPH.DELETE` on an `env:*` graph (it deletes incidents and history).",
    "Loosening an assertion to make a test pass without understanding why the behaviour changed.",
    "Changing `weights.json` to fix one case (weights are versioned; tune on the dev split in phase 10).",
    "Editing generated files by hand (`web/lib/api-types.ts`: run `npm run gen:api`).",
]


def pytest_addoption(parser):
    parser.addoption("--no-report", action="store_true", help="don't write data/reports/<n>-<utc>/*.md")


class Collector:
    def __init__(self) -> None:
        self.results: list[dict] = []
        self.t0 = datetime.now(UTC)

    @pytest.hookimpl
    def pytest_runtest_logreport(self, report) -> None:
        # one row per test: the call phase, or setup / teardown when they failed or skipped
        if report.when != "call" and report.outcome == "passed":
            return
        if report.when == "teardown" and report.outcome != "failed":
            return
        path, line, message = report.location[0], (report.location[1] or 0) + 1, ""
        if report.outcome == "failed":
            crash = getattr(report.longrepr, "reprcrash", None)
            if crash is not None:
                path, line, message = _rel(crash.path), crash.lineno, crash.message
            else:
                message = str(report.longrepr)
        elif report.outcome == "skipped" and isinstance(report.longrepr, tuple):
            message = str(report.longrepr[2])
        self.results.append({"nodeid": report.nodeid, "outcome": report.outcome, "when": report.when,
                             "duration": round(report.duration, 3), "file": path, "line": line,
                             "message": message.strip()})  # fmt: skip

    @pytest.hookimpl(trylast=True)
    def pytest_sessionfinish(self, session, exitstatus) -> None:
        if not self.results:
            return
        meta = run_meta(self.t0, datetime.now(UTC), int(exitstatus), session.config.invocation_params.args)
        out = write(REPORTS, self.results, meta)
        tr = session.config.pluginmanager.get_plugin("terminalreporter")
        if tr is not None:
            tr.write_line(f"report: {out.relative_to(ROOT)}/findings.md, agent-context.md")


def pytest_configure(config):
    if not config.getoption("--no-report", default=False) and not hasattr(config, "workerinput"):
        config.pluginmanager.register(Collector(), "epicenter-report")


def _rel(p: str) -> str:
    try:
        return str(Path(p).resolve().relative_to(ROOT)).replace("\\", "/")
    except ValueError:
        return p


def _git(*args: str) -> str | None:
    try:
        r = subprocess.run(["git", *args], cwd=ROOT, capture_output=True, text=True, timeout=5)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def run_meta(t0: datetime, t1: datetime, exitstatus: int, args) -> dict:
    try:
        weights = json.loads((ROOT / "weights.json").read_text(encoding="utf-8"))["version"]
    except (OSError, ValueError, KeyError):
        weights = None
    dirty = _git("status", "--porcelain")
    return {
        "started": t0.isoformat(timespec="seconds"),
        "duration_s": round((t1 - t0).total_seconds(), 1),
        "exitstatus": exitstatus,
        "args": " ".join(args) or "(all tests)",
        "git": _git("rev-parse", "--short", "HEAD")
        or os.environ.get("GIT_SHA")
        or "unknown (no git in this container)",
        "dirty": None if dirty is None else len(dirty.splitlines()),
        "falkordb_tag": os.environ.get("FALKORDB_TAG", "unknown"),
        "weights": weights,
    }


def next_dir(base: Path, now: datetime) -> Path:
    """`<n>-<utc>`, n one past the highest existing number: reports are kept, never overwritten."""
    nums = [int(m.group(1)) for d in base.glob("*") if (m := re.match(r"(\d+)-", d.name))] if base.exists() else []
    return base / f"{max(nums, default=0) + 1:04d}-{now.strftime('%Y%m%dT%H%M%SZ')}"


def write(base: Path, results: list[dict], meta: dict) -> Path:
    out = next_dir(base, datetime.now(UTC))
    out.mkdir(parents=True)
    (out / "findings.md").write_text(render_findings(results, meta), encoding="utf-8")
    (out / "agent-context.md").write_text(render_agent_context(results, meta), encoding="utf-8")
    return out


def _counts(rs: list[dict]) -> dict[str, int]:
    out = {"passed": 0, "failed": 0, "skipped": 0}
    for r in rs:
        out[r["outcome"]] = out.get(r["outcome"], 0) + 1
    return out


def _by_file(results: list[dict]) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    for r in results:
        out.setdefault(r["nodeid"].split("::")[0], []).append(r)
    return dict(sorted(out.items()))


def render_findings(results: list[dict], meta: dict) -> str:
    c = _counts(results)
    verdict = "all passed" if not c["failed"] else f"{c['failed']} failed"
    lines = [
        f"# Test findings: {verdict}",
        "",
        f"- **Run:** {meta['started']} UTC, {meta['duration_s']} s, `pytest {meta['args']}`, exit {meta['exitstatus']}",
        f"- **Code:** git `{meta['git']}`" + (f", {meta['dirty']} uncommitted file(s)" if meta.get("dirty") else ""),
        f"- **Pinned:** FalkorDB `{meta['falkordb_tag']}`, weights `{meta['weights']}`",
        f"- **Totals:** {c['passed']} passed · {c['failed']} failed · {c['skipped']} skipped",
        "",
        "## By file",
        "",
        "| File | Passed | Failed | Skipped | Slowest |",
        "|---|---|---|---|---|",
    ]
    for f, rs in _by_file(results).items():
        k = _counts(rs)
        slow = max(rs, key=lambda r: r["duration"])
        lines.append(f"| `{f}` | {k['passed']} | {k['failed']} | {k['skipped']} | "
                     f"{slow['duration']:.2f} s `{slow['nodeid'].split('::')[-1]}` |")  # fmt: skip
    failed = [r for r in results if r["outcome"] == "failed"]
    lines += ["", "## Failures", ""]
    if not failed:
        lines.append("None.")
    for r in failed:
        lines += [f"### `{r['nodeid']}`", "", f"- **Where:** `{r['file']}:{r['line']}` (in {r['when']})",
                  "- **Message:**", "", "```", _tail(r["message"]), "```", ""]  # fmt: skip
    skipped = [r for r in results if r["outcome"] == "skipped"]
    if skipped:
        lines += ["", "## Skipped", ""] + [f"- `{r['nodeid']}`: {r['message'] or 'no reason given'}" for r in skipped]
    slowest = sorted(results, key=lambda r: -r["duration"])[:5]
    lines += ["", "## Slowest", ""] + [f"- {r['duration']:.2f} s `{r['nodeid']}`" for r in slowest]
    return "\n".join(lines) + "\n"


def _tail(msg: str, n: int = 25) -> str:
    return "\n".join(msg.splitlines()[-n:])[-3000:] or "(no message)"


def modules_under_test(test_file: Path) -> list[str]:
    """`api…` modules a test file imports: where a fix most likely goes."""
    try:
        tree = ast.parse(test_file.read_text(encoding="utf-8"))
    except (OSError, SyntaxError):
        return []
    mods = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module and node.module.split(".")[0] == "api":
            # `from api.agents import flow` names a module inside a package; `from api.models import X` a symbol
            pkg = node.module.replace(".", "/")
            for a in node.names:
                mods.add(f"{pkg}/{a.name}.py" if (ROOT / pkg / f"{a.name}.py").exists() else f"{pkg}.py")
        elif isinstance(node, ast.Import):
            mods |= {a.name.replace(".", "/") + ".py" for a in node.names if a.name.split(".")[0] == "api"}
    return sorted(m for m in mods if (ROOT / m).exists())


def render_agent_context(results: list[dict], meta: dict) -> str:
    c = _counts(results)
    failed = [r for r in results if r["outcome"] == "failed"]
    lines = [
        "# Agent context: Epicenter test run",
        "",
        "You are a coding agent (Claude Code, Codex, Cursor or similar) working in the Epicenter repo. This file was",
        "generated by the test run next to it (`findings.md`). Read it top to bottom before changing code.",
        "",
        "## The project in one paragraph",
        "",
        "Epicenter finds where an outage started. It keeps a FalkorDB graph of a production system (services,",
        "operations, calls, changes, owners), searches upstream from an alert for the root cause, checks each",
        'suspect with a **Fault Simulator** ("if this were the cause, what would we see?"), and returns every answer',
        "as a graph path. Python 3.12 / FastAPI / LangGraph in `api/`, Next.js in `web/`, tests in `tests/`",
        "against a real FalkorDB.",
        "",
        "Read first: `AGENTS.md` (rules, layout, commands), then the design section each failure points to below.",
        "When docs and code disagree, `docs/ARCHITECTURE.md`, `HLD.md`, `LLD.md`, `API.md`, `GRAPH_SCHEMA.md` and the",
        "ADRs win; fix the code, or change the doc in the same commit if the design really changed.",
        "",
        "## This run",
        "",
        f"- {c['passed']} passed, **{c['failed']} failed**, {c['skipped']} skipped in {meta['duration_s']} s "
        f"(`pytest {meta['args']}`), git `{meta['git']}`, weights `{meta['weights']}`.",
        "",
        "## What to do",
        "",
    ]
    if not failed:
        lines += ["Nothing failed. If you were asked to change something, keep this suite green and add one runnable",
                  "check for any new logic (AGENTS.md \"Tests\")."]  # fmt: skip
    for i, r in enumerate(failed, 1):
        f = r["nodeid"].split("::")[0]
        stem = Path(f).stem
        mods = modules_under_test(ROOT / f)
        lines += [
            f"### {i}. `{r['nodeid']}`",
            "",
            f"- **Failed at:** `{r['file']}:{r['line']}` during {r['when']}",
            f"- **Specified in:** {SPEC.get(stem, 'docs/LLD.md §12 (test plan)')}",
            f"- **Code under test:** {', '.join(f'`{m}`' for m in mods) or 'see the test imports'}",
            f'- **Rerun just this:** `docker compose exec api pytest "{r["nodeid"]}" -q --no-report`',
            "- **Message:**",
            "",
            "```",
            _tail(r["message"], 15),
            "```",
            "",
            "Steps: read the test and the spec section; reproduce with the rerun command; find the root cause in the",
            "code under test (not in the test); fix it; rerun this test, then the whole file.",
            "",
        ]
    lines += ["## Hard rules (a fix must keep all of them)", ""] + [f"- {x}" for x in RULES]
    lines += ["", "## Don't", ""] + [f"- {x}" for x in DONT]
    lines += [
        "",
        "## Commands",
        "",
        "```bash",
        "docker compose up -d                                  # FalkorDB + API must be up for the tests",
        "docker compose exec api pytest -q                     # all tests; writes a new data/reports/<n>-<utc>/",
        "docker compose exec api ruff check . && docker compose exec api ruff format --check .",
        "cd web && npm test && npm run lint && npx tsc --noEmit  # web unit tests, lint, types",
        "```",
        "",
        "## Done when",
        "",
        "- The failing tests above pass, and the full suite is green",
        "  (`pytest`, `ruff`, web `npm test` / `lint` / `tsc`).",
        "- Any design change is written back into the doc that specifies it (and an ADR if it reverses a decision).",
        "- Nothing is committed unless the user asked for a commit.",
    ]
    return "\n".join(lines) + "\n"
