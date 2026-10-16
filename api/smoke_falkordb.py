"""FalkorDB feature check on the pinned tag (phase 0, LLD §12 smoke row).

python -m api.smoke_falkordb   → one PASS/FAIL line per check, exit 1 on any failure.

A diagnostic, not product code: it sends literal Cypher straight to a throwaway `smoke:<uuid>` graph instead of going
through graph.py's catalogue, because its job is to prove the Cypher shapes the catalogue will use.
"""

import sys
import threading
import time
import uuid
from collections.abc import Callable

from falkordb import FalkorDB

from api.config import get_settings

# a → b → c (callers to callees). c went bad first, the problem moved up to a.
FIXTURE = """
CREATE (a:Operation {id:'a'}), (b:Operation {id:'b'}), (c:Operation {id:'c'}), (x:Operation {id:'x'}),
       (a)-[:CALLS {rps: 5.0}]->(b), (b)-[:CALLS {rps: 3.0}]->(c), (a)-[:CALLS {rps: 1.0}]->(x),
       (:Anomaly {id:'an-a', incident:'i1', onset:30, score:0.7, kind:'latency'})-[:ON]->(a),
       (:Anomaly {id:'an-b', incident:'i1', onset:20, score:0.8, kind:'latency'})-[:ON]->(b),
       (:Anomaly {id:'an-c', incident:'i1', onset:10, score:0.9, kind:'errors'})-[:ON]->(c)
"""

# LLD §2.2 Q1 and Q2, verbatim
Q1 = """
MATCH p = (sym:Operation {id: $symptom})-[:CALLS*1..6]->(cand:Operation)
MATCH (a:Anomaly {incident: $inc})-[:ON]->(cand)
WITH cand, min(length(p)) AS hops, min(a.onset) AS onset, max(a.score) AS strength,
     collect(DISTINCT a.kind) AS kinds
RETURN cand.id AS op, hops, onset, strength, kinds
ORDER BY onset, op
"""

Q2 = """
MATCH p = (sym:Operation {id: $symptom})-[:CALLS*1..6]->(cand:Operation {id: $cand})
WITH p, nodes(p) AS ops
UNWIND range(0, size(ops) - 1) AS i
WITH p, i, ops[i] AS n
OPTIONAL MATCH (a:Anomaly {incident: $inc})-[:ON]->(n)
WITH p, i, n, min(a.onset) AS onset
ORDER BY i
WITH p, collect(n.id) AS path, collect(onset) AS onsets
RETURN path, onsets
"""


def rows(g, q: str, **params) -> list[list]:
    return g.query(q, params).result_set


def eventually(fn: Callable[[], list], timeout_s: float = 20.0) -> list:
    # Index creation is asynchronous in FalkorDB and slows down when the host is busy (e.g. a Docker build):
    # poll until a deadline, not a fixed number of tries.
    deadline = time.monotonic() + timeout_s
    while True:
        if out := fn():
            return out
        if time.monotonic() > deadline:
            return []
        time.sleep(0.25)


def check_var_length(g) -> str:
    got = rows(g, Q1, symptom="a", inc="i1")
    assert [(r[0], r[1]) for r in got] == [("c", 2), ("b", 1)], got
    return "Q1: c@2 hops, b@1 hop; x filtered out"


def check_q2_shape(g) -> str:
    got = rows(g, Q2, symptom="a", cand="c", inc="i1")
    assert got == [[["a", "b", "c"], [30, 20, 10]]], got
    return "path [a,b,c], onsets [30,20,10]"


def check_pagerank(g) -> str:
    rows(g, "MATCH (x:Operation)-[c:CALLS]->(y:Operation) CREATE (x)-[:BLAME {w: c.rps}]->(y)")
    got = rows(
        g, "CALL algo.pageRank('Operation', 'BLAME') YIELD node, score RETURN node.id, score ORDER BY score DESC"
    )
    assert got and got[0][0] in ("c", "x"), got
    weighted = []
    for sig in (
        "CALL algo.pageRank('Operation', 'BLAME', 'w') YIELD node, score RETURN node.id, score",
        "CALL algo.pageRank('Operation', 'BLAME', {weightAttribute: 'w'}) YIELD node, score RETURN node.id, score",
    ):
        try:
            rows(g, sig)
            weighted.append(sig.split(" YIELD")[0])
        except Exception:
            pass
    return (
        f"algo.pageRank('Operation','BLAME') YIELD node, score; top={got[0][0]}; "
        f"weighted={'yes: ' + weighted[0] if weighted else 'no'}"
    )


def check_vector(g) -> str:
    rows(
        g, "CREATE VECTOR INDEX FOR (i:Incident) ON (i.signature) OPTIONS {dimension: 4, similarityFunction: 'cosine'}"
    )
    rows(
        g,
        "UNWIND $rows AS r CREATE (:Incident {id: r.id, signature: vecf32(r.v)})",
        rows=[{"id": "near", "v": [1.0, 0.0, 0.0, 0.0]}, {"id": "far", "v": [0.0, 0.0, 1.0, 0.0]}],
    )
    got = eventually(
        lambda: rows(
            g,
            "CALL db.idx.vector.queryNodes('Incident', 'signature', 2, vecf32($v)) "
            "YIELD node, score RETURN node.id, score",
            v=[0.9, 0.1, 0.0, 0.0],
        )
    )
    assert got and got[0][0] == "near", got
    return f"nearest={got[0][0]} score={got[0][1]:.3f}"


def check_fulltext(g) -> str:
    rows(g, "CALL db.idx.fulltext.createNodeIndex('Runbook', 'text')")
    rows(g, "CREATE (:Runbook {id:'rb-1', text:'restart redis primary'}), (:Runbook {id:'rb-2', text:'scale mongo'})")
    got = eventually(lambda: rows(g, "CALL db.idx.fulltext.queryNodes('Runbook', 'redis') YIELD node RETURN node.id"))
    assert [r[0] for r in got] == ["rb-1"], got
    return "query 'redis' → rb-1"


def check_parallel_writers(g) -> str:
    errors: list[Exception] = []

    def write(tag: str) -> None:
        try:
            for i in range(50):
                rows(g, "CREATE (:W {tag: $tag, i: $i})", tag=tag, i=i)
        except Exception as e:  # surfaced below; a thread can't fail the check itself
            errors.append(e)

    threads = [threading.Thread(target=write, args=(t,)) for t in ("w1", "w2")]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert not errors, errors
    got = rows(g, "MATCH (w:W) RETURN w.tag, count(*) ORDER BY w.tag")
    assert got == [["w1", 50], ["w2", 50]], got
    return "2 threads × 50 writes, all present"


CHECKS = [
    ("variable-length path + end filter", check_var_length),
    ("Q2 shape (UNWIND nodes(p) + OPTIONAL MATCH)", check_q2_shape),
    ("algo.pageRank", check_pagerank),
    ("vector index + vecf32", check_vector),
    ("full-text index", check_fulltext),
    ("two parallel writers", check_parallel_writers),
]


def run_all(url: str | None = None) -> list[tuple[str, bool, str]]:
    db = FalkorDB.from_url(url or get_settings().falkordb_url)
    results = []
    for name, check in CHECKS:
        g = db.select_graph(f"smoke:{uuid.uuid4().hex[:8]}")
        try:
            rows(g, FIXTURE)
            results.append((name, True, check(g)))
        except Exception as e:
            results.append((name, False, f"{type(e).__name__}: {e}"))
        finally:
            try:
                g.delete()
            except Exception:
                pass
    return results


def main() -> int:
    db = FalkorDB.from_url(get_settings().falkordb_url)
    print(
        f"FalkorDB {db.connection.info('server').get('redis_version')} · modules: "
        f"{[(m.get('name'), m.get('ver')) for m in db.connection.module_list()]}"
    )
    results = run_all()
    for name, ok, note in results:
        print(f"{'PASS' if ok else 'FAIL'}  {name}: {note}")
    passed = sum(ok for _, ok, _ in results)
    print(f"{passed}/{len(results)} PASS")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
