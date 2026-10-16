"""The change journal every examples/*/faults.py writes **before** it acts (api/ingest/changes.py reads it).

One JSON object per line in examples/run/changes.jsonl; the API container sees it read-only at
/app/examples/run/changes.jsonl (CHANGE_JOURNAL).
"""

import json
import time
from pathlib import Path

JOURNAL = Path(__file__).resolve().parent / "run" / "changes.jsonl"


def record(env: str, service: str, service_kind: str, type_: str, summary: str, ref: str,
           change_id: str | None = None) -> dict:  # fmt: skip
    ts = int(time.time())
    entry = {"id": change_id or f"chg-{env}-{ts}", "env": env, "service": service, "service_kind": service_kind,
             "type": type_, "ts": ts, "summary": summary, "ref": ref}  # fmt: skip
    JOURNAL.parent.mkdir(parents=True, exist_ok=True)
    with JOURNAL.open("a", encoding="utf-8") as f:
        f.write(json.dumps(entry, sort_keys=True) + "\n")
        f.flush()
    return entry
