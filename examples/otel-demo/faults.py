"""OTel Demo fault scenarios (EXAMPLE_RUNS §1): flagd feature flags. flagd watches its flag file, so a flag flips in
about a second. Like every faults.py, the change is journaled **before** the flag flips.

    python examples/otel-demo/faults.py <scenario> [--undo] [--change-id ID]
"""

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent))
sys.path.insert(0, str(HERE))

import journal  # noqa: E402
import run  # noqa: E402

ENV = "astronomy-shop"
# scenario → (flag, variant when on, service the flag acts on)
SCENARIOS = {
    "paymentFailure": ("paymentFailure", "50%", "payment"),
    "adHighCpu": ("adHighCpu", "on", "ad"),
    "emailMemoryLeak": ("emailMemoryLeak", "100x", "email"),
}


def set_flag(flag: str, variant: str) -> None:
    doc = json.loads(run.FLAGS.read_text(encoding="utf-8"))
    if variant not in doc["flags"][flag]["variants"]:
        raise SystemExit(f"{flag} has no variant {variant!r}: {sorted(doc['flags'][flag]['variants'])}")
    doc["flags"][flag]["defaultVariant"] = variant
    tmp = run.FLAGS.with_suffix(".tmp")
    tmp.write_text(json.dumps(doc, indent=2) + "\n", encoding="utf-8")
    tmp.replace(run.FLAGS)  # one rename: flagd never reads a half-written file


def main() -> None:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("scenario", choices=sorted(SCENARIOS))
    p.add_argument("--undo", action="store_true")
    p.add_argument("--change-id")
    a = p.parse_args()
    flag, variant, service = SCENARIOS[a.scenario]
    if a.undo:
        set_flag(flag, "off")
        print(f"flag {flag} → off")
        return
    journal.record(ENV, service, "app", "flag", f"flag {flag} → {variant}", f"faults.py:{a.scenario}", a.change_id)
    set_flag(flag, variant)
    print(f"flag {flag} → {variant}")


if __name__ == "__main__":
    main()
