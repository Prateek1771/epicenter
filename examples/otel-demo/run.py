"""Run the OpenTelemetry Demo for Epicenter (EXAMPLE_RUNS §1). The demo's clone is read, never edited, except the
flagd flag file that `faults.py` flips (that's how the demo injects its faults).

    python examples/otel-demo/run.py up       demo + observability layer + Epicenter's port layer, the fault runner
    python examples/otel-demo/run.py status   JSON health
    python examples/otel-demo/run.py down     stop it (containers stopped, volumes kept)

The demo is upstream's, pinned at tag 3.1.0 and never edited here. `up` clones it into the git-ignored
`examples/otel-demo/upstream/` on first use; `DEMO_DIR`, or an existing sibling `../opentelemetry-demo` clone, wins.
Stop flip-commerce first: both want ports 8080 and 4317.
"""

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

HERE = Path(__file__).resolve().parent
EXAMPLES = HERE.parent
REPO_URL, TAG = "https://github.com/open-telemetry/opentelemetry-demo", "3.1.0"
PROJECT = "opentelemetry-demo"  # fixed: the compose project must not change with the clone's folder name


def demo_dir() -> Path:
    if os.environ.get("DEMO_DIR"):
        return Path(os.environ["DEMO_DIR"])
    sibling = EXAMPLES.parent.parent / "opentelemetry-demo"  # the layout the earlier setup guide used
    return sibling if (sibling / "compose.yaml").exists() and not (HERE / "upstream").exists() else HERE / "upstream"


def clone_cmd(dest: Path) -> list[str]:
    return ["git", "clone", "--depth", "1", "--branch", TAG, REPO_URL, str(dest)]


def fetch() -> None:
    """Clone the pinned demo on the first `up`. Only the flag file that faults.py flips is ever edited in it."""
    if (DEMO / "compose.yaml").exists():
        return
    print(f"fetching the OpenTelemetry Demo {TAG} into {DEMO} …", flush=True)
    subprocess.run(clone_cmd(DEMO), check=True)


DEMO = demo_dir()
FLAGS = DEMO / "src" / "flagd" / "demo.flagd.json"
FRONTEND = "http://127.0.0.1:8080"


def compose(*args: str, check: bool = True) -> str:
    files = ["-f", str(DEMO / "compose.yaml"), "-f", str(DEMO / "compose.observability.yaml"),
             "-f", str(HERE / "compose.epicenter.yaml")]  # fmt: skip
    r = subprocess.run(["docker", "compose", "-p", PROJECT, "--project-directory", str(DEMO), *files, *args],
                       capture_output=True, text=True)  # fmt: skip
    if check and r.returncode != 0:
        raise SystemExit(r.stdout + r.stderr)
    return r.stdout


def get(url: str, timeout: float = 2.0) -> int:
    try:
        with urllib.request.urlopen(url, timeout=timeout) as r:
            return r.status
    except urllib.error.HTTPError as e:
        return e.code
    except OSError:
        return 0


def flags() -> dict[str, str]:
    return {k: v["defaultVariant"] for k, v in json.loads(FLAGS.read_text(encoding="utf-8"))["flags"].items()}


def ready() -> bool:
    # a static file, not "/": the home page renders through product-catalog, seconds slow under load
    return (get(f"{FRONTEND}/favicon.ico", timeout=2.0) == 200
            and get("http://127.0.0.1:16686/jaeger/ui/api/services", timeout=2.0) == 200)  # fmt: skip


def status() -> dict:
    running = subprocess.run(["docker", "ps", "--format", "{{.Names}}"], capture_output=True, text=True).stdout.split()
    on = {k: v for k, v in flags().items() if v not in ("off", False)} if FLAGS.exists() else {}
    return {
        "frontend": get(f"{FRONTEND}/"),
        "jaeger": get("http://127.0.0.1:16686/jaeger/ui/api/services"),
        "prometheus": get("http://127.0.0.1:9090/-/ready"),
        "opensearch": get("http://127.0.0.1:9200/"),
        "load_generator": "load-generator" in running,
        "flags_on": on,
        "up": ready(),
    }


def up() -> None:
    fetch()
    compose("up", "-d")
    end = time.time() + 600
    while time.time() < end and not ready():
        time.sleep(5)
    sys.path.insert(0, str(EXAMPLES / "flip-commerce"))
    import run as flip  # the shared process helpers (pid files, detached spawn)

    if not flip.alive("runner"):
        flip.start_runner()
    print(json.dumps(status(), indent=2))


def down() -> None:
    compose("stop", check=False)  # never `down -v`


if __name__ == "__main__":
    cmd = sys.argv[1] if len(sys.argv) > 1 else "status"
    if cmd == "up":
        up()
    elif cmd == "down":
        down()
    elif cmd == "ready":
        print(json.dumps({"up": ready()}))
    else:
        print(json.dumps(status(), indent=2))
