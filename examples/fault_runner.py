"""Host-side fault runner (ADR 0012): the only way the API reaches an example environment.

    python examples/fault_runner.py            (run.py up starts it)

The API runs in a container without the Docker socket and can't restart host processes, so `POST /runs` asks this
process to run `examples/<env>/faults.py`. Every request needs `X-Runner-Token` = FAULT_RUNNER_TOKEN from the repo's
.env. It runs only the registered fault scripts, with arguments it validates; nothing else.

    GET  /health   {"envs": {"flip-commerce": true, "astronomy-shop": false}}
    POST /fault    {"env", "scenario", "undo", "change_id"} → {"ok", "output"}
"""

import hmac
import json
import os
import re
import subprocess
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
ENVS = {"flip-commerce": HERE / "flip-commerce", "astronomy-shop": HERE / "otel-demo"}
_ID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.:-]{0,80}$")
PORT = int(os.environ.get("FAULT_RUNNER_PORT", "8090"))


def token() -> str:
    """FAULT_RUNNER_TOKEN from the environment, else from the repo's .env (never logged, never sent back)."""
    if t := os.environ.get("FAULT_RUNNER_TOKEN"):
        return t
    env = HERE.parent / ".env"
    for line in env.read_text(encoding="utf-8").splitlines() if env.exists() else []:
        if line.startswith("FAULT_RUNNER_TOKEN="):
            return line.split("=", 1)[1].split("#", 1)[0].strip()
    return ""


TOKEN = token()


def env_up(env: str) -> bool:
    d = ENVS[env]
    if not (d / "run.py").exists():
        return False
    r = subprocess.run([sys.executable, str(d / "run.py"), "ready"], capture_output=True, text=True, timeout=10)
    try:
        return bool(json.loads(r.stdout).get("up"))
    except ValueError:
        return False


class Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: dict) -> None:
        data = json.dumps(body).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _authorized(self) -> bool:
        ok = bool(TOKEN) and hmac.compare_digest(self.headers.get("X-Runner-Token", ""), TOKEN)
        if not ok:
            self._send(401, {"ok": False, "output": "missing or wrong X-Runner-Token"})
        return ok

    def do_GET(self) -> None:  # noqa: N802
        if self.path != "/health":
            return self._send(404, {"ok": False})
        if self._authorized():
            self._send(200, {"envs": {e: env_up(e) for e in sorted(ENVS)}})

    def do_POST(self) -> None:  # noqa: N802
        if self.path != "/fault":
            return self._send(404, {"ok": False})
        if not self._authorized():
            return
        try:
            body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))))
            env, scenario = str(body["env"]), str(body["scenario"])
        except (ValueError, KeyError):
            return self._send(400, {"ok": False, "output": "body: {env, scenario, undo, change_id}"})
        change_id = body.get("change_id")
        if env not in ENVS or not _ID.match(scenario) or (change_id is not None and not _ID.match(str(change_id))):
            return self._send(400, {"ok": False, "output": "unknown env or bad id"})
        args = [sys.executable, str(ENVS[env] / "faults.py"), scenario]
        args += ["--undo"] if body.get("undo") else []
        args += ["--change-id", str(change_id)] if change_id else []
        try:
            # UTF-8 both ways: a Windows pipe defaults to cp1252, and a script that printed "→" after acting
            # reported a fault that was already in as failed
            r = subprocess.run(args, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=140,
                               cwd=ENVS[env], env={**os.environ, "PYTHONIOENCODING": "utf-8"})  # fmt: skip
        except subprocess.TimeoutExpired:
            return self._send(200, {"ok": False, "output": "fault script timed out after 140 s"})
        out = (r.stdout + r.stderr).strip()[-2000:]
        self._send(200, {"ok": r.returncode == 0, "output": out})

    def log_message(self, fmt: str, *args) -> None:
        sys.stderr.write("fault_runner: " + (fmt % args) + "\n")


if __name__ == "__main__":
    if not TOKEN:
        raise SystemExit("set FAULT_RUNNER_TOKEN in .env first")
    # Docker Desktop's host.docker.internal reaches the host's loopback-bound ports, so the API container can call
    # this without exposing it on the LAN; FAULT_RUNNER_BIND=0.0.0.0 for a Linux docker0 setup (still token-gated).
    ThreadingHTTPServer((os.environ.get("FAULT_RUNNER_BIND", "127.0.0.1"), PORT), Handler).serve_forever()
