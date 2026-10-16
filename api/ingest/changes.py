"""Change journal (LLD §3.1): the record `examples/*/faults.py` writes **before** it acts, one JSON object per line.

    {"id": "chg-…", "env": "flip-commerce", "service": "mongodb", "service_kind": "datastore", "type": "infra",
     "ts": 1760600000, "summary": "docker stop fk-mongo-primary", "ref": "faults.py:mongo-primary-down"}

The same shape is what a deploy or CI webhook would post later; only the transport changes.
"""

import json
from pathlib import Path

from api.ingest.base import ChangeEvent


def read_journal(path: Path, env: str, since: int) -> list[ChangeEvent]:
    if not path.exists():
        return []
    out = []
    with path.open(encoding="utf-8") as f:
        for line in f:
            try:
                d = json.loads(line)
            except ValueError:
                continue
            if d.get("env") != env or int(d.get("ts", 0)) < since:
                continue
            out.append(
                ChangeEvent(
                    id=str(d["id"]),
                    service=str(d["service"]),
                    type=str(d["type"]),
                    ts=int(d["ts"]),
                    summary=str(d.get("summary", "")),
                    ref=d.get("ref"),
                    service_kind=str(d.get("service_kind", "app")),
                )
            )
    return sorted(out, key=lambda c: (c.ts, c.id))
