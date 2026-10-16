"""Drain3 log-template anomalies, shared by every adapter (LLD §3.2 "Logs").

Per service: a template that is **new** in the window → `new_template`; a template whose rate grows ≥ `log_ratio`×
with ≥ `log_min` occurrences in the window → `log_burst`. Returns anomalies keyed by service; the caller attaches them
to an operation. Deterministic: lines are fed in (service, ts, text) order and Signal ids hash the template text.
"""

import hashlib
import re
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from drain3 import TemplateMiner
from drain3.masking import MaskingInstruction
from drain3.template_miner_config import TemplateMinerConfig

from api.ingest.base import LogLine
from api.ingest.detect import to_score

# Spring Boot prefix: "2024-01-23 15:14:51.239  INFO 1 --- [io-12340-exec-2] auth.service.impl.TokenServiceImpl  : msg"
_PREFIX = re.compile(r"^\d{4}-\d\d-\d\d[ T][\d:.,]+\s+\w+\s+\d+\s+---\s+\[[^\]]*\]\s+")
_MASKS = [
    MaskingInstruction(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}", "UUID"),
    MaskingInstruction(r"[A-Za-z0-9_\-]{24,}(\.[A-Za-z0-9_\-]+)*", "TOKEN"),
    MaskingInstruction(r"0x[0-9a-fA-F]+|\b[0-9a-fA-F]{12,}\b", "HEX"),
    MaskingInstruction(r"\d+(\.\d+)?", "NUM"),
]


@dataclass
class LogAnomaly:
    service: str
    kind: str  # new_template · log_burst
    onset: int
    score: float
    signal: str  # Signal id
    template: str


def _miner() -> TemplateMiner:
    cfg = TemplateMinerConfig()
    cfg.masking_instructions = _MASKS
    cfg.profiling_enabled = False
    return TemplateMiner(config=cfg)


def signal_id(service: str, template: str) -> str:
    return f"log:{service}:{hashlib.sha1(template.encode()).hexdigest()[:12]}"


def detect_logs(
    lines: Iterable[LogLine], base: tuple[int, int], window: tuple[int, int], cfg: dict
) -> list[LogAnomaly]:
    per_service: dict[str, list[LogLine]] = defaultdict(list)
    for ln in lines:
        if base[0] <= ln.ts <= window[1]:
            per_service[ln.service].append(ln)
    base_len, win_len = max(base[1] - base[0], 1), max(window[1] - window[0], 1)
    out = []
    for svc in sorted(per_service):
        miner = _miner()
        base_n: dict[int, int] = defaultdict(int)
        win_n: dict[int, int] = defaultdict(int)
        win_ts: dict[int, list[int]] = defaultdict(list)
        for ln in sorted(per_service[svc], key=lambda x: (x.ts, x.text)):
            cid = miner.add_log_message(_PREFIX.sub("", ln.text))["cluster_id"]
            if ln.ts < base[1]:
                base_n[cid] += 1
            elif ln.ts >= window[0]:
                win_n[cid] += 1
                win_ts[cid].append(ln.ts)
        templates = {c.cluster_id: c.get_template() for c in miner.drain.clusters}
        for cid in sorted(win_n):
            n = win_n[cid]
            if base_n[cid] == 0:
                kind, ratio, onset = "new_template", float(n), win_ts[cid][0]
            else:
                ratio = (n / win_len) / (base_n[cid] / base_len)
                if ratio < cfg["log_ratio"] or n < cfg["log_min"]:
                    continue
                kind = "log_burst"
                onset = burst_onset(win_ts[cid], base_n[cid] / base_len, cfg)
            t = templates[cid]
            out.append(LogAnomaly(svc, kind, onset, to_score(ratio), signal_id(svc, t), t))
    return out


def burst_onset(ts: list[int], base_rate: float, cfg: dict) -> int:
    """First bucket whose count reaches `log_ratio`× the baseline rate: when the burst started, not the template's
    first line in the window (a template that was already chatty would otherwise "start" at the window edge)."""
    step = cfg["bucket_s"]
    need = max(1.0, cfg["log_ratio"] * base_rate * step)
    counts: dict[int, int] = defaultdict(int)
    for t in ts:
        counts[t // step * step] += 1
    return next((b for b in sorted(counts) if counts[b] >= need), ts[0])
