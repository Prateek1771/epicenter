"""Run flip-commerce for Epicenter, on the host, without modifying its repo (EXAMPLE_RUNS §2).

    python examples/flip-commerce/run.py up       Mongo (repo compose), Redis + collector + nginx, flip-node with OTel,
                                                  sample data, normal k6 load, the fault runner
    python examples/flip-commerce/run.py status   JSON health of every part
    python examples/flip-commerce/run.py down     stop everything (containers are stopped, data volumes kept)

`FLIP_REPO` points at `season-1/2.vertical-vs-horizontal-scaling` (default: D:\\vertical_scaling\\...).
"""

import json
import os
import secrets
import shutil
import signal
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent
RUN = HERE / "run"
DEFAULT_REPO = r"D:\vertical_scaling\system-design-journey\season-1\2.vertical-vs-horizontal-scaling"
REPO = Path(os.environ.get("FLIP_REPO", DEFAULT_REPO))
NODE_DIR = REPO / "servers" / "01-node"
MONGO_COMPOSE = NODE_DIR / "infra" / "mongo" / "compose.yaml"
REGISTER = (
    HERE
    / "otel-node"
    / "node_modules"
    / "@opentelemetry"
    / "auto-instrumentations-node"
    / "build"
    / "src"
    / "register.js"
)
MONGO_URI = (
    "mongodb://127.0.0.1:27017,127.0.0.1:27018,127.0.0.1:27019/flip-commerce"
    "?replicaSet=fk-rs&w=majority&retryWrites=true&readPreference=primaryPreferred"
)
NODE_URL = "http://127.0.0.1:5001"
NGINX_URL = "http://127.0.0.1:8080"
NORMAL_RATE = 20  # requests / s: "normal 100 VUs" scaled to one laptop worker
_DETACH = (subprocess.CREATE_NEW_PROCESS_GROUP | subprocess.DETACHED_PROCESS) if os.name == "nt" else 0  # type: ignore[attr-defined]


def sh(*args: str, check: bool = True, quiet: bool = False) -> str:
    r = subprocess.run(args, capture_output=True, text=True)
    if check and r.returncode != 0:
        raise SystemExit(f"$ {' '.join(args)}\n{r.stdout}{r.stderr}")
    return r.stdout if quiet else (r.stdout + r.stderr)


def get(url: str, timeout: float = 2.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def wait(url: str, ok=(200,), timeout_s: int = 90) -> bool:
    end = time.time() + timeout_s
    while time.time() < end:
        if get(url) in ok:
            return True
        time.sleep(1)
    return False


# --- background processes (pid files in run/) ---


def _pidfile(name: str) -> Path:
    return RUN / f"{name}.pid"


def alive(name: str) -> bool:
    f = _pidfile(name)
    if not f.exists():
        return False
    pid = int(f.read_text())
    if os.name == "nt":
        out = sh("tasklist", "/FI", f"PID eq {pid}", "/NH", check=False, quiet=True)
        return str(pid) in out
    try:
        os.kill(pid, 0)
        return True
    except OSError:
        return False


def spawn(name: str, args: list[str], cwd: Path, env: dict | None = None) -> int:
    (RUN / "logs").mkdir(parents=True, exist_ok=True)
    out = (RUN / "logs" / f"{name}.out").open("ab")
    p = subprocess.Popen(args, cwd=cwd, env={**os.environ, **(env or {})}, stdout=out, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, creationflags=_DETACH)  # fmt: skip
    _pidfile(name).write_text(str(p.pid))
    return p.pid


def kill(name: str) -> None:
    f = _pidfile(name)
    if not f.exists():
        return
    pid = int(f.read_text())
    if os.name == "nt":
        sh("taskkill", "/PID", str(pid), "/T", "/F", check=False)  # /T: node's cluster workers too
    else:
        try:
            os.killpg(pid, signal.SIGTERM)
        except OSError:
            pass
    f.unlink(missing_ok=True)


# --- parts ---


def secrets_env() -> dict:
    """JWT secrets for flip-node, generated once per checkout (run/ is git-ignored)."""
    f = RUN / "secrets.json"
    if not f.exists():
        RUN.mkdir(parents=True, exist_ok=True)
        f.write_text(
            json.dumps({"JWT_ACCESS_SECRET": secrets.token_hex(32), "JWT_REFRESH_SECRET": secrets.token_hex(32)})
        )
    return json.loads(f.read_text())


def node_env(overrides: dict | None = None) -> dict:
    env = {
        "NODE_ENV": "production",  # winston writes JSON
        "LOG_LEVEL": "http",
        "PORT": "5001",
        "WORKERS": "1",
        "MONGO_URI": MONGO_URI,
        "REDIS_URL": "redis://127.0.0.1:6379",
        "OTEL_SERVICE_NAME": "flip-node",
        "OTEL_EXPORTER_OTLP_ENDPOINT": "http://127.0.0.1:4318",
        "OTEL_EXPORTER_OTLP_PROTOCOL": "http/protobuf",
        "OTEL_TRACES_EXPORTER": "otlp",
        "OTEL_METRICS_EXPORTER": "none",
        "OTEL_LOGS_EXPORTER": "none",
        "OTEL_NODE_RESOURCE_DETECTORS": "env,host",
        "OTEL_BSP_SCHEDULE_DELAY": "1000",
        # fs / dns / net spans are noise for operation-level aggregation
        "OTEL_NODE_DISABLED_INSTRUMENTATIONS": "fs,dns,net",
    } | secrets_env()
    return env | (overrides or {})


def start_node(overrides: dict | None = None, wait_healthy: bool = True) -> None:
    """flip-node from the repo's built dist/, with OTel loaded from examples/ (--import), cwd run/node for its logs.
    `wait_healthy=False`: a bad config is expected to keep it from booting."""
    kill("node")
    cwd = RUN / "node"
    (cwd / "logs").mkdir(parents=True, exist_ok=True)
    (RUN / "node-config.json").write_text(json.dumps(overrides or {}, sort_keys=True))
    args = ["node", "--import", REGISTER.as_uri(), str(NODE_DIR / "dist" / "server.js")]
    spawn("node", args, cwd, node_env(overrides))
    if wait_healthy and not wait(f"{NODE_URL}/health", timeout_s=120):  # first boot waits for the replica set to elect
        raise SystemExit(f"flip-node didn't come up; see {RUN / 'logs' / 'node.out'}")


def mongo_up() -> None:
    sh("docker", "compose", "-f", str(MONGO_COMPOSE), "-p", "fk", "up", "-d", "--wait",
       "mongo-primary", "mongo-secondary-1", "mongo-secondary-2")  # fmt: skip
    # one-shot replica-set init (skips itself once the set exists)
    sh("docker", "compose", "-f", str(MONGO_COMPOSE), "-p", "fk", "up", "mongo-init", check=False)


def seed_products(n: int = 200) -> None:
    import urllib.request as rq

    with rq.urlopen(f"{NODE_URL}/products?limit=1", timeout=5) as r:
        if json.loads(r.read()).get("items"):
            return
    for i in range(n):
        body = json.dumps({"name": f"Epicenter sample {i}", "description": "seeded by run.py", "price": 10 + i % 90,
                           "stock": 100, "category": ["phones", "books", "home", "toys"][i % 4],
                           "imageUrl": f"https://example.invalid/{i}.png"}).encode()  # fmt: skip
        rq.urlopen(rq.Request(f"{NODE_URL}/products", body, {"Content-Type": "application/json"}), timeout=5).read()


def start_load(rate: int = NORMAL_RATE, name: str = "k6", duration: str = "4h") -> None:
    kill(name)
    k6 = shutil.which("k6") or r"C:\Program Files\k6\k6.exe"
    spawn(name, [k6, "run", "--quiet", "--summary-mode=disabled", str(HERE / "load.js")], HERE,
          {"BASE": NGINX_URL, "RATE": str(rate), "DURATION": duration, "K6_NO_USAGE_REPORT": "true"})  # fmt: skip


def start_runner() -> None:
    if alive("runner"):
        return
    spawn("runner", [sys.executable, str(EXAMPLES / "fault_runner.py")], EXAMPLES)


# --- commands ---


def up() -> None:
    RUN.mkdir(exist_ok=True)
    for d in ("otel", "nginx"):
        (RUN / d).mkdir(exist_ok=True)
    if not REGISTER.exists():
        sh("npm", "ci", "--no-audit", "--no-fund", "--prefix", str(HERE / "otel-node"))
    mongo_up()
    sh("docker", "compose", "-f", str(HERE / "compose.yaml"), "up", "-d", "--wait")
    start_node()
    seed_products()
    if not wait(f"{NGINX_URL}/node/health", timeout_s=30):
        raise SystemExit("nginx can't reach flip-node on host.docker.internal:5001")
    start_load()
    start_runner()
    print(json.dumps(status(), indent=2))


def down() -> None:
    for name in ("k6-stress", "k6", "node", "runner"):
        kill(name)
    sh("docker", "compose", "-f", str(HERE / "compose.yaml"), "down", check=False)  # never -v
    sh("docker", "compose", "-f", str(MONGO_COMPOSE), "-p", "fk", "stop", check=False)


def mongo_members() -> dict[str, str]:
    """container → state (PRIMARY / SECONDARY / down), asked of any member that answers."""
    names = {"host.docker.internal:27017": "fk-mongo-primary", "host.docker.internal:27018": "fk-mongo-secondary-1",
             "host.docker.internal:27019": "fk-mongo-secondary-2"}  # fmt: skip
    js = "JSON.stringify(rs.status().members.map(m => [m.name, m.stateStr]))"
    for c in names.values():
        out = sh("docker", "exec", c, "mongosh", "--quiet", "--eval", js, check=False, quiet=True).strip()
        if out.startswith("["):
            return {names.get(n, n): s for n, s in json.loads(out)}
    return {c: "down" for c in names.values()}


def status() -> dict:
    running = sh("docker", "ps", "--format", "{{.Names}}", check=False, quiet=True).split()
    st = {
        "mongo": mongo_members(),
        "redis": "fk-redis" in running,
        "collector": "fk-otel-collector" in running,
        "nginx": get(f"{NGINX_URL}/health") == 200,
        "node_ready": get(f"{NODE_URL}/ready"),
        "node_config": json.loads(cfg.read_text()) if (cfg := RUN / "node-config.json").exists() else {},
        "load": alive("k6"),
        "stress": alive("k6-stress"),
        "runner": alive("runner"),
    }
    st["up"] = bool(st["nginx"] and alive("node") and st["load"])
    return st


def ready() -> bool:
    """The fast check the fault runner's /health uses: app process, nginx and load (no docker exec)."""
    return get(f"{NGINX_URL}/health", timeout=1.0) == 200 and alive("node") and alive("k6")


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "up":
        up()
    elif cmd == "down":
        down()
    elif cmd == "ready":
        print(json.dumps({"up": ready()}))
    elif cmd == "load":
        start_load(int(sys.argv[2]) if len(sys.argv) > 2 else NORMAL_RATE)
    else:
        print(json.dumps(status(), indent=2))
