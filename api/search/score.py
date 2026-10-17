"""Deterministic scoring (LLD §6). Pure functions: hypothesis facts in, features / scores / ranking out.

score = Σ w·features − 1.0·refuted;  confidence = sigmoid(k·(s1 − s2)), s2 = 0 when there is one hypothesis.
Continuous features are rank-normalized within the incident (average rank for ties), so their scale never depends on
the system's units. The LLM never reaches this module (ADR 0002).
"""

import json
import math
from functools import lru_cache
from pathlib import Path

FEATURES = ("onset_earliness", "strength", "mechanism_fit", "pagerank", "change_match", "footprint")
SELF_CAUSED_KINDS = {"cpu", "mem", "down", "errors"}
ABLATIONS = {"temporal", "mechanism"}  # rules the eval can switch off (phase 10); weights alone can't remove a refute


@lru_cache
def load_weights(path: str) -> dict:
    """weights.json, validated: every feature has a weight, the weights sum to 1, the rule params are there."""
    w = json.loads(Path(path).read_text(encoding="utf-8"))
    missing = [k for k in ("version", "w", "k", "skew_s", "lookback_s") if k not in w]
    if missing:
        raise ValueError(f"{path}: missing {missing}")
    unknown = set(w["w"]) - set(FEATURES)
    if unknown:
        raise ValueError(f"{path}: unknown features {sorted(unknown)}")
    if abs(sum(w["w"].values()) - 1.0) > 1e-6:
        raise ValueError(f"{path}: weights sum to {sum(w['w'].values())}, expected 1")
    bad = set(w.get("ablate", [])) - ABLATIONS
    if bad:
        raise ValueError(f"{path}: unknown ablations {sorted(bad)}")
    return w


def rank_normalize(values: list[float | None]) -> list[float]:
    """Higher value → closer to 1. Ties share their average rank; None ranks last (0). One value → 1."""
    present = sorted({v for v in values if v is not None})
    if not present:
        return [0.0] * len(values)
    n = sum(v is not None for v in values)
    if n == 1:
        return [1.0 if v is not None else 0.0 for v in values]
    below: dict[float, float] = {}
    seen = 0
    for v in present:
        same = sum(x == v for x in values)
        below[v] = seen + (same - 1) / 2  # average 0-based rank of the tied group
        seen += same
    return [round(below[v] / (n - 1), 6) if v is not None else 0.0 for v in values]


def mechanism_fit(kinds: list[str], victim: bool, self_caused: bool | None) -> float:
    """1 self-caused (self ≥ child time, or a kind that is its own mechanism); 0 victim; 0.5 otherwise."""
    if victim:
        return 0.0
    if self_caused or set(kinds) & SELF_CAUSED_KINDS:
        return 1.0
    return 0.5


def features(hyps: list[dict]) -> list[dict]:
    """hyps: dicts with onset, strength, kinds, victim, self_caused, change, pagerank, footprint, refuted."""
    earliness = rank_normalize([-h["onset"] if h["onset"] is not None else None for h in hyps])
    # 2 decimals: anomaly scores carry no meaning past that, and ranking would turn 0.9999 vs 1.0 into 0.5 vs 1.0
    strength = rank_normalize([None if h["strength"] is None else round(h["strength"], 2) for h in hyps])
    pagerank = rank_normalize([h["pagerank"] for h in hyps])
    out = []
    for i, h in enumerate(hyps):
        out.append(
            {
                "onset_earliness": earliness[i],
                "strength": strength[i],
                "mechanism_fit": mechanism_fit(h["kinds"], h["victim"], h["self_caused"]),
                "pagerank": pagerank[i],
                "change_match": 1.0 if h["change"] else 0.0,
                "footprint": round(float(h.get("footprint", 0.0)), 6),
                "refuted": 1.0 if h["refuted"] else 0.0,
            }
        )
    return out


def score(f: dict, w: dict) -> float:
    return round(sum(w["w"].get(k, 0.0) * f[k] for k in FEATURES) - 1.0 * f["refuted"], 6)


def confidence(scores: list[float], k: float) -> float:
    """sigmoid(k·(s1 − s2)) over the two best scores; s2 = 0 with a single hypothesis."""
    if not scores:
        return 0.0
    top = sorted(scores, reverse=True)
    s2 = top[1] if len(top) > 1 else 0.0
    return round(1.0 / (1.0 + math.exp(-k * (top[0] - s2))), 6)


def ranking(hyps: list[dict]) -> list[dict]:
    """Tie-break: higher score, then earlier onset, then operation id."""
    return sorted(hyps, key=lambda h: (-h["score"], h["onset"] if h["onset"] is not None else math.inf, h["op"]))


def score_parts_json(f: dict, extra: dict) -> str:
    """Byte-stable JSON (sorted keys, rounded floats) stored on the Hypothesis."""
    return json.dumps({**f, **extra}, sort_keys=True, separators=(",", ":"))
