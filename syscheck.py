"""System evaluator (phase 11, LLD §13): what can this machine run? Probe -> tier -> recommend -> (run) -> report.

    python syscheck.py                    probe, pick a tier, print the runs that fit (changes nothing)
    python syscheck.py --run              start Epicenter and run the tier's offline checks (never an example env)
    python syscheck.py --run --live       + the live tiers: asks y/N per environment (--yes-envs: don't ask)
    python syscheck.py --tier 2 --minutes 20 --json

Stdlib only (Python ≥ 3.10): it runs before anything is installed. Reports go to data/syscheck/<n>-<utc>/ (report.json,
findings.md, agent-context.md), numbered, never overwritten; .env values are never read into them, only key names.
Exit: 0 all passed | 1 a check failed or a verdict differed | 2 below tier 1 or no Docker.
"""

from __future__ import annotations

import argparse
import ctypes
import json
import os
import platform
import shutil
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent
API = "http://localhost:8000/api/v1"
GB = 1024**3
CORE_PORTS = [6380, 3002, 8081, 8000, 3001, 3000]
ENV_PORTS = [8080, 16686, 9090, 9200, 8090]
REF_OPS = 20_000_000  # 3 s single-thread loop: the dev laptop scores 1.8-2.2x; below 0.4x drops a tier
MEM_SLACK = 0.9  # Docker reports usable memory: a VM set to 16 GB shows ~15.3 GiB

# LLD §13.2, one row per tier: all conditions must hold, on min(host, Docker VM)
TIERS = [
    {"tier": 1, "name": "Small", "cpus": 2, "mem_gb": 4, "disk_gb": 10, "needs": [], "minutes": 5},
    {"tier": 2, "name": "Medium", "cpus": 4, "mem_gb": 8, "disk_gb": 20, "needs": ["internet"], "minutes": 15},
    {"tier": 3, "name": "Real-world", "cpus": 8, "mem_gb": 16, "disk_gb": 40, "needs": ["demo_dir"], "minutes": 30},
]

# the three demos (SETUP §5): what each tier adds; `live` items only with --live. expect: from /runs/scenarios
PLAN = {
    1: [  # small: synthetic, a known answer on any laptop
        ("smoke", "docker compose exec -T api python -m api.smoke_falkordb", None),
        ("selftest", "docker compose exec -T api python -m api.selftest", None),
        ("synthetic small", "synth:small:cpu,healthy", None),
        (
            "pytest (offline subset)",
            "docker compose exec -T api pytest -q --no-report tests/test_simulate.py "
            "tests/test_causal.py tests/test_score.py tests/test_spans.py tests/test_detect.py",
            None,
        ),
    ],
    2: [  # medium: RCAEval Train-Ticket, real recorded faults
        ("pytest (full)", "docker compose exec -T api pytest -q --no-report", None),
        (
            "RCAEval replays",
            "replay:rcaeval-tt:re2tt_ts-auth-service_cpu_2,re2tt_ts-order-service_delay_1,re2tt_ts-auth-service_cpu_1",
            None,
        ),
        ("N2 query p95", "n2", None),
    ],
    3: [("OTel Demo", "live:astronomy-shop:paymentFailure,adHighCpu", None)],  # real-world: live faults
}
RUN_DIRS = {"flip-commerce": "flip-commerce", "astronomy-shop": "otel-demo"}


# --- probe (read-only) ---


def sh(*cmd: str, timeout: float = 30) -> tuple[int, str]:
    try:
        p = subprocess.run(cmd, cwd=ROOT, capture_output=True, text=True, timeout=timeout)
        return p.returncode, (p.stdout + p.stderr).strip()
    except (OSError, subprocess.TimeoutExpired) as e:
        return 127, str(e)


def host_mem() -> int:
    if sys.platform == "win32":

        class MS(ctypes.Structure):
            _fields_ = [
                ("len", ctypes.c_ulong),
                ("load", ctypes.c_ulong),
                ("total", ctypes.c_ulonglong),
                ("avail", ctypes.c_ulonglong),
                ("tp", ctypes.c_ulonglong),
                ("ap", ctypes.c_ulonglong),
                ("tv", ctypes.c_ulonglong),
                ("av", ctypes.c_ulonglong),
                ("ax", ctypes.c_ulonglong),
            ]

        m = MS()
        m.len = ctypes.sizeof(MS)
        ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
        return m.total
    if sys.platform == "darwin":
        return int(sh("sysctl", "-n", "hw.memsize")[1] or 0)
    for line in Path("/proc/meminfo").read_text().splitlines():
        if line.startswith("MemTotal:"):
            return int(line.split()[1]) * 1024
    return 0


def http(url: str, timeout: float = 3, method: str = "GET", body: dict | None = None) -> tuple[int, dict | str]:
    req = urllib.request.Request(
        url,
        method=method,
        data=json.dumps(body).encode() if body else None,
        headers={"content-type": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, json.loads(raw) if raw.startswith(("{", "[")) else raw
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()[:300]
    except (OSError, ValueError) as e:
        return 0, str(e)


def port_free(port: int) -> bool:
    with socket.socket() as s:
        return s.connect_ex(("127.0.0.1", port)) != 0


def bench() -> dict:
    t0, n = time.perf_counter(), 0
    while time.perf_counter() - t0 < 3:
        for _ in range(10_000):
            n += 1
    ops = n / (time.perf_counter() - t0) * 3
    f = ROOT / "data" / ".syscheck-bench"
    f.parent.mkdir(exist_ok=True)
    block = os.urandom(1 << 20)
    t0 = time.perf_counter()
    with open(f, "wb") as fh:
        for _ in range(256):
            fh.write(block)
        fh.flush()
        os.fsync(fh.fileno())
    mbps = 256 / (time.perf_counter() - t0)
    f.unlink(missing_ok=True)
    return {"cpu_x_ref": round(ops / REF_OPS, 2), "disk_mb_s": round(mbps)}


def env_keys() -> dict:
    """Names only: which keys are set, and whether any still says change-me. Values never leave this function."""
    p = ROOT / ".env"
    if not p.exists():
        return {"present": False}
    kv = dict(
        ln.split("=", 1) for ln in p.read_text(encoding="utf-8").splitlines() if "=" in ln and not ln.startswith("#")
    )
    clean = {k.strip(): v.split("#", 1)[0].strip().strip("'\"") for k, v in kv.items()}
    return {
        "present": True,
        "change_me": sorted(k for k, v in clean.items() if v == "change-me"),
        "set": sorted(k for k, v in clean.items() if v),
    }


def probe() -> dict:
    disk = shutil.disk_usage(ROOT)
    rc, dv = sh("docker", "version", "--format", "{{.Server.Version}}")
    docker = rc == 0
    cv = sh("docker", "compose", "version", "--short")[1] if docker else ""
    vm_cpus = vm_mem = 0
    if docker:
        out = sh("docker", "info", "--format", "{{.NCPU}} {{.MemTotal}}")[1].split()
        vm_cpus, vm_mem = (int(out[0]), int(out[1])) if len(out) == 2 and out[0].isdigit() else (0, 0)
    code, health = http(f"{API}/health")
    p = {
        "os": f"{platform.system()} {platform.release()}",
        "arch": platform.machine(),
        "host_cpus": os.cpu_count() or 0,
        "host_mem_gb": round(host_mem() / GB, 1),
        "disk_free_gb": round(disk.free / GB, 1),
        "docker": dv if docker else None,
        "compose": cv or None,
        "vm_cpus": vm_cpus,
        "vm_mem_gb": round(vm_mem / GB, 1),
        "tools": {t: bool(shutil.which(t)) for t in ("git", "node", "k6", "uv")},
        "internet": {h: http(f"https://{h}", 3, "HEAD")[0] not in (0,) for h in ("huggingface.co", "openrouter.ai")},
        "ports_busy": [pt for pt in CORE_PORTS + ENV_PORTS if not port_free(pt)],
        "env": env_keys(),
        "stack": health if code == 200 else None,
        "flip_repo": bool(os.environ.get("FLIP_REPO")) or Path(r"D:\vertical_scaling\system-design-journey").exists(),
        # the OTel Demo: already cloned, or fetchable (examples/otel-demo/run.py up clones the pinned tag with git)
        "demo_dir": bool(os.environ.get("DEMO_DIR")) or (ROOT / "examples" / "otel-demo" / "upstream").exists()
        or (ROOT.parent / "opentelemetry-demo").exists() or bool(shutil.which("git")),
    }
    p["bench"] = bench()
    return p


# --- tier (pure) ---


def pick_tier(p: dict, explicit: int | None = None) -> tuple[int, str]:
    """Highest tier whose every condition holds on min(host, Docker VM). -> (tier, what capped it)."""
    if not p.get("docker"):
        return 0, "Docker is not running"
    cpus = min(p["host_cpus"], p["vm_cpus"] or p["host_cpus"])
    mem = min(p["host_mem_gb"], p["vm_mem_gb"] or p["host_mem_gb"])
    have = {"internet": all(p["internet"].values()), "demo_dir": p.get("demo_dir", False)}
    best, why = 0, ""
    for t in TIERS:
        short = [f"{cpus} CPUs < {t['cpus']}"] if cpus < t["cpus"] else []
        short += [f"{mem} GB memory < {t['mem_gb']}"] if mem < t["mem_gb"] * MEM_SLACK else []
        short += [f"{p['disk_free_gb']} GB disk < {t['disk_gb']}"] if p["disk_free_gb"] < t["disk_gb"] else []
        short += [f"needs {n}" for n in t["needs"] if not have[n]]
        if short:
            why = f"tier {t['tier']} needs: " + ", ".join(short)
            break
        best = t["tier"]
    if best and p.get("bench", {}).get("cpu_x_ref", 1) < 0.4:
        best, why = best - 1, f"slow CPU ({p['bench']['cpu_x_ref']}x the reference): one tier down"
    if explicit is not None:
        return min(explicit, max(best, 1)) if best else 0, why or f"--tier {explicit}"
    return best, why or "every tier's conditions hold"


# --- run ---


class Report:
    def __init__(self) -> None:
        self.rows: list[dict] = []

    def add(
        self, check: str, ok: bool, expected: str = "", got: str = "", ms: float = 0, cmd: str = "", spec: str = ""
    ) -> None:
        self.rows.append({"check": check, "ok": ok, "expected": expected, "got": got, "s": round(ms / 1000, 1),
                          "cmd": cmd, "spec": spec})  # fmt: skip
        print(f"  {'PASS' if ok else 'FAIL'}  {check:<44} {expected[:28]:<28} -> {got[:40]:<40} {ms / 1000:6.1f} s")


def timed(cmd: str, timeout: float = 1800) -> tuple[int, str, float]:
    t0 = time.perf_counter()
    try:
        p = subprocess.run(cmd, cwd=ROOT, shell=True, capture_output=True, text=True, timeout=timeout,
                           encoding="utf-8", errors="replace")  # fmt: skip
        return p.returncode, (p.stdout + p.stderr).strip(), (time.perf_counter() - t0) * 1000
    except subprocess.TimeoutExpired:
        return 124, "timeout", (time.perf_counter() - t0) * 1000


def wait_incident(inc: str, env: str, deadline: float) -> dict:
    while time.time() < deadline:
        code, d = http(f"{API}/incidents/{inc}?env={env}", 10)
        if code == 200 and isinstance(d, dict) and d.get("status") not in ("open", "diagnosing"):
            return d
        time.sleep(3)
    return {"status": "timeout"}


def verdict_of(d: dict) -> tuple[str, str | None]:
    v = d.get("verdict") or {}
    return d.get("status", "?"), (v.get("root_cause") or {}).get("target")


def matches(expect: dict | None, status: str, rc: str | None) -> bool:
    if not expect:
        return status in ("diagnosed", "no_root_cause")
    if "status" in expect:
        return status == expect["status"]
    return rc is not None and rc.startswith(expect["target_prefix"])


def scenario_expects() -> dict[tuple[str, str], dict]:
    code, d = http(f"{API}/runs/scenarios", 10)
    return {(s["env"], s["id"]): s.get("expect") for s in d["items"]} if code == 200 else {}


def run_synth(rep: Report, size: str, faults: list[str]) -> None:
    if not (ROOT / "examples" / "synthetic" / "gen.py").exists():
        rep.add(f"synthetic {size}", False, "", "examples/synthetic/gen.py missing", 0, "", "EXAMPLE_RUNS §4")
        return
    for f in faults:
        cmd = f"docker compose exec -T api python examples/synthetic/gen.py --size {size} --fault {f} --seed 1 --run"
        rc, out, ms = timed(cmd)
        last = out.strip().splitlines()[-1] if out.strip() else ""
        try:
            r = json.loads(last)
            ok = r["ok"]
            rep.add(f"synthetic {size} {f}", ok, r["expected"], r["got"], ms, cmd, "EXAMPLE_RUNS §4")
        except (ValueError, KeyError):
            rep.add(f"synthetic {size} {f}", False, "verdict", last[:60] or f"exit {rc}", ms, cmd, "EXAMPLE_RUNS §4")


def run_replays(rep: Report, env: str, cases: list[str]) -> None:
    for c in cases:
        svc = c.split("_", 1)[1].rsplit("_", 2)[0]
        replay = f"docker compose exec -T api python -m api.ingest.rcaeval --case {c} --env {env} --download"
        rc, out, ms = timed(replay)
        if rc:
            rep.add(f"RCAEval {c}", False, f"{svc}/*", (out.splitlines() or [f"exit {rc}"])[-1][:60], ms, replay,
                    "EXAMPLE_RUNS §3")  # fmt: skip
            continue
        # through the API, like the UI: the same path, and its queries feed /health (the N2 check reads them)
        cmd = f"POST {API}/incidents/rc-{c}/diagnose?env={env}&force=true"
        t0 = time.perf_counter()
        http(f"{API}/incidents/rc-{c}/diagnose?env={env}&force=true", 10, "POST")
        v: dict = {}
        while time.perf_counter() - t0 < 120:
            time.sleep(1)
            _, d = http(f"{API}/incidents/rc-{c}?env={env}", 10)
            if isinstance(d, dict) and d.get("status") not in (None, "open", "diagnosing"):
                v = d
                break
        got = ((v.get("verdict") or {}).get("root_cause") or {}).get("target") or v.get("status") or "timeout"
        ms2 = (time.perf_counter() - t0) * 1000
        rep.add(
            f"RCAEval {c}", str(got).startswith(svc + "/"), f"{svc}/*", str(got), ms + ms2, cmd, "EXAMPLE_RUNS §3"
        )  # a miss is reported, not hidden: RE2-TT AC@1 is 87.8%, not 100%


def run_live(rep: Report, env: str, ids: list[str], yes: bool) -> None:
    run_py = f"{sys.executable} examples/{RUN_DIRS[env]}/run.py"
    if (
        not yes
        and input(f"\n  Start {env} and inject {', '.join(ids)}? Each fault is undone after. [y/N] ").lower() != "y"
    ):
        rep.add(f"{env} (live)", True, "skipped", "skipped by you", 0, "", "EXAMPLE_RUNS")
        return
    rc, out, ms = timed(f"{run_py} up", 1200)
    if rc:
        rep.add(f"{env} up", False, "up", out[-80:], ms, f"{run_py} up", "EXAMPLE_RUNS")
        return
    print("  waiting 10 min of normal load (the detector's baseline window)...")
    time.sleep(600)
    expects = scenario_expects()
    for sid in ids:
        t0 = time.perf_counter()
        code, run = http(f"{API}/runs", 30, "POST", {"env": env, "scenario": sid})
        if code != 202 or not isinstance(run, dict):
            rep.add(f"{env} {sid}", False, "202", str(run)[:60], 0, "", "API.md runs")
            continue
        try:
            alert = datetime.fromisoformat(run["alert_at"].replace("Z", "+00:00")).timestamp()
            d = wait_incident(run["incident_id"], env, alert + 240)
            status, rc_op = verdict_of(d)
            exp = expects.get((env, sid))
            want = (
                exp.get("target_prefix", "") + "*" if exp and "target_prefix" in exp else (exp or {}).get("status", "")
            )
            rep.add(
                f"{env} {sid}",
                matches(exp, status, rc_op),
                want,
                rc_op or status,
                (time.perf_counter() - t0) * 1000,
                f"POST /runs {sid}",
                "EXAMPLE_RUNS",
            )
        finally:
            http(f"{API}/runs/{run['run_id']}?env={env}", 30, "DELETE")  # undo, whatever happened
            time.sleep(30)
        if sid != ids[-1]:
            time.sleep(570)  # a clean baseline before the next fault
    timed(f"{run_py} down", 600)


def do_run(tier: int, live: bool, yes: bool) -> Report:
    rep = Report()
    services = "falkordb api web" if tier == 1 else ""
    rc, out, ms = timed(f"docker compose up -d {services}".strip(), 1800)
    rep.add("docker compose up", rc == 0, "exit 0", f"exit {rc}", ms, "docker compose up -d", "SETUP §3")
    if rc:
        return rep
    for _ in range(60):
        if http(f"{API}/health")[0] == 200:
            break
        time.sleep(3)
    for t in range(1, tier + 1):
        for name, what, _ in PLAN[t]:
            if what.startswith("synth:"):
                _, size, faults = what.split(":")
                run_synth(rep, size, faults.split(","))
            elif what.startswith("replay:"):
                _, env, cases = what.split(":")
                run_replays(rep, env, cases.split(","))
            elif what == "n2":
                code, h = http(f"{API}/health")
                q = h.get("query_ms", {}) if isinstance(h, dict) else {}
                worst = max((v["p95"] for k, v in q.items() if k[:2] in ("Q1", "Q2", "Q3", "Q4", "Q5")), default=None)
                rep.add(
                    name,
                    worst is not None and worst < 200,
                    "< 200 ms",
                    f"{worst} ms",
                    0,
                    "GET /health",
                    "ARCHITECTURE §1.2 N2",
                )
            elif what.startswith("live:"):
                if live:
                    _, env, ids = what.split(":")
                    run_live(rep, env, ids.split(","), yes)
            else:
                rc, out, ms = timed(what)
                tail = out.strip().splitlines()[-1] if out.strip() else ""
                rep.add(name, rc == 0, "exit 0", tail[:60] or f"exit {rc}", ms, what, "LLD §13")
    return rep


# --- report ---


def recommend(tier: int, minutes: int, live: bool) -> list[str]:
    out, budget = [], minutes
    for t in TIERS:
        if t["tier"] > tier or t["minutes"] > budget:
            break
        budget -= t["minutes"]
        for name, what, _ in PLAN[t["tier"]]:
            if what.startswith("live:") and not live:
                out.append(f"tier {t['tier']}: {name} (add --live)")
            else:
                out.append(f"tier {t['tier']}: {name}")
    return out


def write_report(p: dict, tier: int, why: str, rep: Report | None) -> Path:
    base = ROOT / "data" / "syscheck"
    base.mkdir(parents=True, exist_ok=True)
    n = 1 + max((int(d.name.split("-", 1)[0]) for d in base.iterdir() if d.name[:4].isdigit()), default=0)
    out = base / f"{n:04d}-{datetime.now(UTC):%Y%m%dT%H%M%SZ}"
    out.mkdir()
    rows = rep.rows if rep else []
    (out / "report.json").write_text(json.dumps({"probe": p, "tier": tier, "why": why, "checks": rows}, indent=1),
                                     encoding="utf-8")  # fmt: skip
    lines = [f"# syscheck {out.name}", "",
             f"Tier **{tier}** ({why}). Docker VM {p['vm_cpus']} CPUs / {p['vm_mem_gb']} GB,"
             f" host {p['host_cpus']} / {p['host_mem_gb']} GB, disk free {p['disk_free_gb']} GB.", "",
             "| Check | Result | Expected | Got | s |", "|---|---|---|---|---|"]  # fmt: skip
    lines += [f"| {r['check']} | {'pass' if r['ok'] else '**FAIL**'} | {r['expected']} | {r['got']} | {r['s']} |"
              for r in rows]  # fmt: skip
    (out / "findings.md").write_text("\n".join(lines) + "\n", encoding="utf-8")
    failed = [r for r in rows if not r["ok"]]
    guide = [
        "# Agent context (syscheck)",
        "",
        "Read AGENTS.md first. For each failed check: the spec, then the rerun.",
        "",
    ]
    guide += [f"- **{r['check']}**: expected `{r['expected']}`, got `{r['got']}`. Spec: {r['spec']}."
              f" Rerun: `{r['cmd']}`" for r in failed] or ["Nothing failed."]  # fmt: skip
    (out / "agent-context.md").write_text("\n".join(guide) + "\n", encoding="utf-8")
    return out


def main(argv: list[str] | None = None) -> int:
    a = argparse.ArgumentParser(description="Epicenter system evaluator (LLD §13)")
    a.add_argument("--run", action="store_true")
    a.add_argument("--live", action="store_true")
    a.add_argument("--tier", type=int)
    a.add_argument("--minutes", type=int, default=30)
    a.add_argument("--json", action="store_true")
    a.add_argument("--yes-envs", action="store_true")
    args = a.parse_args(argv)
    print("probing (~15 s)")
    p = probe()
    tier, why = pick_tier(p, args.tier)
    if args.json and not args.run:
        print(json.dumps({"probe": p, "tier": tier, "why": why}, indent=1))
        return 0 if tier else 2
    print(
        f"\n  {p['os']} {p['arch']} | host {p['host_cpus']} CPUs / {p['host_mem_gb']} GB | Docker VM "
        f"{p['vm_cpus']} CPUs / {p['vm_mem_gb']} GB | disk free {p['disk_free_gb']} GB"
        f" | CPU {p['bench']['cpu_x_ref']}x ref"
    )
    if p["env"].get("change_me"):
        print(f"  warning: .env still has change-me for {', '.join(p['env']['change_me'])}")
    print(f"\n  TIER {tier}: {TIERS[tier - 1]['name'] if tier else 'below Small'} ({why})")
    if not tier:
        print("  This machine can't run the stack. Use the hosted demo URL or the recorded video (SETUP.md).")
        return 2
    print(f"\n  Recommended (fits --minutes {args.minutes}):")
    for r in recommend(tier, args.minutes, args.live):
        print(f"    {r}")
    rep = None
    if args.run:
        print("\n  Running:")
        rep = do_run(tier, args.live, args.yes_envs)
    out = write_report(p, tier, why, rep)
    print(f"\n  report: {out}")
    return 0 if rep is None or all(r["ok"] for r in rep.rows) else 1


if __name__ == "__main__":
    sys.exit(main())
