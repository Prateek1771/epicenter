"""examples/otel-demo/run.py: the demo is fetched at the pinned tag, and DEMO_DIR wins over the default."""

import importlib.util
from pathlib import Path

RUN = Path(__file__).resolve().parents[1] / "examples" / "otel-demo" / "run.py"


def load():
    spec = importlib.util.spec_from_file_location("otel_run", RUN)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_demo_is_fetched_pinned_and_overridable(monkeypatch, tmp_path):
    monkeypatch.setenv("DEMO_DIR", str(tmp_path / "demo"))
    run = load()
    assert run.DEMO == tmp_path / "demo" and run.FLAGS == tmp_path / "demo" / "src" / "flagd" / "demo.flagd.json"
    cmd = run.clone_cmd(tmp_path / "x")
    assert cmd[:2] == ["git", "clone"] and cmd[cmd.index("--branch") + 1] == "3.1.0" and "--depth" in cmd
    assert run.PROJECT == "opentelemetry-demo"  # the compose project never follows the folder name
    monkeypatch.delenv("DEMO_DIR")
    assert load().DEMO.name in ("upstream", "opentelemetry-demo")
