"""The only module that talks to FalkorDB (AGENTS.md rule 2).

Callers pass a query id from QUERIES plus parameters, never Cypher text. Every call is timed, logged and fed into a
per-query ring buffer that /health reports as p50/p95.
"""

import json
import logging
import time
from collections import defaultdict, deque
from pathlib import Path

from falkordb import FalkorDB
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

log = logging.getLogger("epicenter.graph")

KB_GRAPH = "kb:propagation"

QUERIES: dict[str, str] = {
    # --- Upserts (LLD §2.1) ---
    "U1": """
        MERGE (cs:Service {name: $caller_svc})
        MERGE (co:Operation {id: $caller_op}) ON CREATE SET co.name = $caller_name
        MERGE (cs)-[:HAS_OP]->(co)
        MERGE (ts:Service {name: $callee_svc}) ON CREATE SET ts.kind = $callee_kind
        MERGE (to:Operation {id: $callee_op}) ON CREATE SET to.name = $callee_name
        MERGE (ts)-[:HAS_OP]->(to)
        MERGE (co)-[c:CALLS]->(to)
        SET c.rps = $rps, c.p95_ms = $p95_ms, c.err_rate = $err_rate, c.last_seen = $ts,
            co.last_seen = $ts, to.last_seen = $ts""",
    "U2": """
        MATCH (o:Operation {id: $op})
        CREATE (a:Anomaly {id: $id, incident: $incident, kind: $kind, onset: $onset, score: $score,
                           self_ratio: $self_ratio, child_ratio: $child_ratio, ref: $ref,
                           detector: $detector})-[:ON]->(o)""",
    "U3": """
        MATCH (s:Service {name: $service})
        MERGE (c:Change {id: $id}) ON CREATE SET c.type = $type, c.ts = $ts, c.summary = $summary, c.ref = $ref
        MERGE (c)-[:CHANGED {ts: $ts}]->(s)""",
    # Batched forms for ingest (one round trip per tick; rows sorted by the caller)
    "U1_batch": """
        UNWIND $rows AS r
        MERGE (cs:Service {name: r.caller_svc}) ON CREATE SET cs.kind = 'app'
        MERGE (co:Operation {id: r.caller_op}) ON CREATE SET co.name = r.caller_name
        MERGE (cs)-[:HAS_OP]->(co)
        MERGE (ss:Service {name: r.callee_svc}) ON CREATE SET ss.kind = r.callee_kind
        MERGE (so:Operation {id: r.callee_op}) ON CREATE SET so.name = r.callee_name
        MERGE (ss)-[:HAS_OP]->(so)
        MERGE (co)-[c:CALLS]->(so)
        SET c.rps = r.rps, c.p95_ms = r.p95_ms, c.err_rate = r.err_rate, c.last_seen = $ts,
            co.last_seen = $ts, so.last_seen = $ts, cs.last_seen = $ts, ss.last_seen = $ts""",
    "U2_batch": """
        UNWIND $rows AS r
        MATCH (o:Operation {id: r.op})
        CREATE (a:Anomaly {id: r.id, incident: $incident, kind: r.kind, onset: r.onset, score: r.score,
                           detector: r.detector})-[:ON]->(o)
        SET a.self_ratio = r.self_ratio, a.child_ratio = r.child_ratio, a.ref = r.ref""",
    # Operations seen only in signals (no caller→callee pair yet), so U2's MATCH never silently drops an anomaly
    "U6_ops": """
        UNWIND $rows AS r
        MERGE (s:Service {name: r.svc}) ON CREATE SET s.kind = 'app'
        MERGE (o:Operation {id: r.op}) ON CREATE SET o.name = r.name
        MERGE (s)-[:HAS_OP]->(o)""",
    "U4_open_incident": """
        MERGE (i:Incident {id: $id})
        SET i.status = 'open', i.symptom = $symptom, i.opened_at = $opened_at,
            i.weights_version = $weights_version, i.gaps = $gaps""",
    "U5_signal": """
        UNWIND $rows AS r
        MERGE (s:Signal {id: r.signal}) ON CREATE SET s.type = 'log_template', s.text = r.text
        WITH s, r
        MATCH (a:Anomaly {incident: $incident, id: r.anomaly})
        MERGE (a)-[:IN_SIGNAL]->(s)""",
    "clear_incident_anomalies": "MATCH (a:Anomaly {incident: $inc}) DETACH DELETE a",
    "incident_anomalies": """
        MATCH (a:Anomaly {incident: $inc})-[:ON]->(o:Operation)
        RETURN a.id AS id, o.id AS op, a.kind AS kind, a.onset AS onset, a.score AS score, a.detector AS detector,
               a.self_ratio AS self_ratio, a.child_ratio AS child_ratio, a.ref AS ref
        ORDER BY id""",
    "label_counts": "MATCH (n) RETURN labels(n)[0] AS label, count(*) AS n ORDER BY label",
    # --- Causal search (LLD §2.2) ---
    "Q1": """
        MATCH p = (sym:Operation {id: $symptom})-[:CALLS*1..6]->(cand:Operation)
        MATCH (a:Anomaly {incident: $inc})-[:ON]->(cand)
        WITH cand, min(length(p)) AS hops, min(a.onset) AS onset, max(a.score) AS strength,
             collect(DISTINCT a.kind) AS kinds
        RETURN cand.id AS op, hops, onset, strength, kinds
        ORDER BY onset, op""",
    "Q2": """
        MATCH p = (sym:Operation {id: $symptom})-[:CALLS*1..6]->(cand:Operation {id: $cand})
        WITH p, nodes(p) AS ops
        UNWIND range(0, size(ops) - 1) AS i
        WITH p, i, ops[i] AS n
        OPTIONAL MATCH (a:Anomaly {incident: $inc})-[:ON]->(n)
        WITH p, i, n, min(a.onset) AS onset
        ORDER BY i
        WITH p, collect(n.id) AS path, collect(onset) AS onsets
        RETURN path, onsets""",
    "Q3": """
        MATCH (a:Anomaly {incident: $inc})-[:ON]->(cand:Operation {id: $cand})<-[:HAS_OP]-(s:Service)
        OPTIONAL MATCH (ch:Change)-[:CHANGED]->(s)
          WHERE ch.ts <= a.onset AND ch.ts >= a.onset - $lookback_s
        RETURN a.id AS anomaly, a.kind AS kind, a.self_ratio AS self_ratio, a.child_ratio AS child_ratio,
               collect(ch {.id, .type, .ts, .summary}) AS changes
        ORDER BY anomaly""",
    "Q4a": """
        MATCH (a:Anomaly {incident: $inc})-[:ON]->(o:Operation)
        WITH collect(DISTINCT o) AS ops
        UNWIND ops AS x
        MATCH (x)-[c:CALLS]->(y) WHERE y IN ops
        RETURN x.id AS caller, y.id AS callee, c.err_rate AS err, c.p95_ms AS p95
        ORDER BY caller, callee""",
    # Q4 middle step: write the projection into scratch:<incident>; $edges = [{caller, callee, w}]
    "Q4_blame": """
        UNWIND $edges AS e
        MERGE (x:Operation {id: e.caller})
        MERGE (y:Operation {id: e.callee})
        MERGE (x)-[b:BLAME]->(y) SET b.w = e.w""",
    # Unweighted: v4.22.1 has no weighted form (LLD §2 smoke results)
    "Q4b": """
        CALL algo.pageRank('Operation', 'BLAME') YIELD node, score
        RETURN node.id AS op, score
        ORDER BY score DESC, op""",
    # score is cosine distance: lower = more similar
    "Q5": """
        CALL db.idx.vector.queryNodes('Incident', 'signature', 5, vecf32($sig)) YIELD node AS past, score
        WITH past, score WHERE past.id <> $inc AND past.status = 'resolved'
        MATCH (past)-[:ROOT_CAUSE]->(:Hypothesis)-[:BLAMES]->(cause)
        OPTIONAL MATCH (past)-[:RESOLVED_BY]->(act:Action)
        RETURN past.id AS incident, score, labels(cause)[0] AS cause_type,
               coalesce(cause.id, cause.name) AS cause, collect(act.name) AS fixes
        ORDER BY score, incident""",
    "Q6": """
        MATCH p = (caller:Operation)-[:CALLS*1..6]->(c:Operation {id: $cand})
        WHERE all(r IN relationships(p) WHERE r.rps > 0)
        RETURN caller.id AS op, length(p) AS hops,
               [n IN nodes(p) | n.id] AS path, [r IN relationships(p) | r.rps] AS rps
        ORDER BY hops, op""",
    # --- Tool queries (LLD §2.3) ---
    "blast_radius": """
        MATCH (s:Service {name: $svc})-[:HAS_OP]->(o)
        MATCH p = (caller:Operation)-[:CALLS*1..6]->(o)
        MATCH (cs:Service)-[:HAS_OP]->(caller)
        OPTIONAL MATCH (cs)-[:OWNED_BY]->(t:Team)
        RETURN cs.name AS service, caller.id AS op, min(length(p)) AS hops, t.name AS team
        ORDER BY hops, op""",
    "why_not": """
        MATCH (:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:BLAMES]->(o:Operation)
              <-[:HAS_OP]-(:Service {name: $svc})
        OPTIONAL MATCH (h)-[:REFUTED_BY]->(e:Evidence)
        RETURN h.id AS hypothesis, h.status AS status, o.id AS op,
               collect(e {.id, .kind, .summary, .path}) AS refuted_by
        ORDER BY hypothesis""",
    "recent_changes": """
        MATCH (c:Change)-[:CHANGED]->(:Service {name: $svc})
        WHERE c.ts >= $since
        OPTIONAL MATCH (p:Person)-[:AUTHORED]->(c)
        RETURN c.id AS id, c.type AS type, c.ts AS ts, c.summary AS summary, collect(p.handle) AS authors
        ORDER BY ts DESC, id""",
    # One point per reason: team member, fixed an incident rooted here, authored a change here
    "who_knows": """
        MATCH (s:Service {name: $svc})
        OPTIONAL MATCH (s)-[:OWNED_BY]->(:Team)<-[:MEMBER_OF]-(m:Person)
        WITH s, collect(DISTINCT m) AS members
        OPTIONAL MATCH (f:Person)-[:FIXED]->(:Incident)-[:ROOT_CAUSE]->(:Hypothesis)-[:BLAMES]->(:Operation)
                       <-[:HAS_OP]-(s)
        WITH s, members, collect(f) AS fixers
        OPTIONAL MATCH (a:Person)-[:AUTHORED]->(:Change)-[:CHANGED]->(s)
        WITH members, fixers, collect(a) AS authors
        UNWIND members + fixers + authors AS p
        RETURN p.handle AS handle, p.name AS name, count(*) AS score
        ORDER BY score DESC, handle""",
    # --- Seed (GRAPH_SCHEMA §5, LLD §7.1) ---
    "idx_service": "CREATE INDEX FOR (s:Service) ON (s.name)",
    "idx_operation": "CREATE INDEX FOR (o:Operation) ON (o.id)",
    "idx_anomaly": "CREATE INDEX FOR (a:Anomaly) ON (a.incident)",
    "idx_change": "CREATE INDEX FOR (c:Change) ON (c.ts)",
    "idx_incident": "CREATE INDEX FOR (i:Incident) ON (i.id)",
    "idx_hypothesis": "CREATE INDEX FOR (h:Hypothesis) ON (h.id)",
    "idx_person": "CREATE INDEX FOR (p:Person) ON (p.handle)",
    "idx_simulation": "CREATE INDEX FOR (s:Simulation) ON (s.id)",
    "idx_signal": "CREATE INDEX FOR (s:Signal) ON (s.id)",
    "idx_signal_text": "CALL db.idx.fulltext.createNodeIndex('Signal', 'text')",
    "idx_incident_signature": "CREATE VECTOR INDEX FOR (i:Incident) ON (i.signature) "
    "OPTIONS {dimension: 64, similarityFunction: 'cosine'}",
    "idx_rule": "CREATE INDEX FOR (r:Rule) ON (r.id)",
    "rules_version": "MATCH (r:Rule) RETURN DISTINCT r.version AS version",
    "seed_rule": """
        MERGE (r:Rule {id: $id})
        SET r.cause_kinds = $cause, r.symptom_kind = $symptom, r.direction = $direction,
            r.p = $p, r.delay_s_max = $delay_s_max, r.service_kind = $kind_of_service, r.version = $version""",
    "seed_team": """
        MERGE (t:Team {name: $team})
        WITH t UNWIND $services AS svc
        MERGE (s:Service {name: svc})
        MERGE (s)-[:OWNED_BY]->(t)""",
    "seed_member": """
        MATCH (t:Team {name: $team})
        MERGE (p:Person {handle: $handle}) SET p.name = $name
        MERGE (p)-[:MEMBER_OF]->(t)""",
    "seed_runbook": """
        MERGE (r:Runbook {id: $id})
        ON CREATE SET r.success = '{}'
        SET r.kind = $kind, r.steps = $steps
        WITH r UNWIND $services AS svc
        MERGE (s:Service {name: svc})
        MERGE (r)-[:FOR]->(s)""",
    "count_nodes": "MATCH (n) RETURN count(n) AS n",
    "list_indexes": "CALL db.indexes() YIELD label, properties RETURN label, properties ORDER BY label",
}


class GraphUnavailable(Exception):
    """FalkorDB unreachable after the retry; the API maps it to 503 GRAPH_UNAVAILABLE."""


# ponytail: per-process timings; if the API ever runs as several replicas, /health shows one replica's view
_timings: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=200))


def query_stats() -> dict[str, dict[str, float]]:
    """p50/p95 in ms per query id over its last 200 calls."""
    out = {}
    for qid, ds in sorted(_timings.items()):
        xs = sorted(ds)
        out[qid] = {"p50": round(xs[len(xs) // 2], 1), "p95": round(xs[min(len(xs) - 1, int(len(xs) * 0.95))], 1)}
    return out


class EnvGraph:
    def __init__(self, graph, key: str, timeout_s: float):
        self._g = graph
        self.key = key
        self._timeout_ms = int(timeout_s * 1000)

    def ro(self, qid: str, **params) -> list[dict]:
        try:
            return self._run(qid, params, self._g.ro_query)
        except ResponseError as e:
            if "empty key" in str(e):  # graph not created yet: nothing to read
                return []
            raise

    def rw(self, qid: str, **params) -> list[dict]:
        return self._run(qid, params, self._g.query)

    def delete(self) -> None:
        try:
            self._g.delete()
        except RedisConnectionError as e:
            raise GraphUnavailable(str(e)) from e
        except ResponseError as e:
            if "empty key" not in str(e):  # already gone is fine
                raise

    def load_cypher(self, path: Path) -> None:
        """Run a trusted `;`-separated Cypher file (test fixtures only). The one raw-Cypher entry point."""
        lines = Path(path).read_text(encoding="utf-8").splitlines()
        code = "\n".join(ln for ln in lines if not ln.strip().startswith("//"))
        for stmt in code.split(";"):
            if stmt.strip():
                self._g.query(stmt)

    def _run(self, qid: str, params: dict, fn) -> list[dict]:
        q = QUERIES[qid]
        for attempt in (1, 2):  # LLD §10: one retry, connection errors only
            t0 = time.perf_counter()
            try:
                res = fn(q, params, timeout=self._timeout_ms)
                break
            except (RedisConnectionError, RedisTimeoutError) as e:
                if attempt == 2:
                    raise GraphUnavailable(f"{qid} on {self.key}: {e}") from e
        ms = (time.perf_counter() - t0) * 1000
        cols = [h[1] for h in res.header]
        rows = [dict(zip(cols, r, strict=True)) for r in res.result_set]
        _timings[qid].append(ms)
        log.info(json.dumps({"qid": qid, "graph": self.key, "duration_ms": round(ms, 1), "rows": len(rows)}))
        return rows


class Graph:
    def __init__(self, url: str, timeout_s: float = 5.0):
        self._url = url
        self._timeout_s = timeout_s
        self._conn: FalkorDB | None = None

    @property
    def _db(self) -> FalkorDB:
        # Lazy: the client connects on construction, and the API must start (degraded) while FalkorDB is down.
        if self._conn is None:
            try:
                self._conn = FalkorDB.from_url(
                    self._url, socket_timeout=self._timeout_s, socket_connect_timeout=self._timeout_s
                )
            except (RedisConnectionError, RedisTimeoutError) as e:
                raise GraphUnavailable(str(e)) from e
        return self._conn

    def _select(self, key: str) -> EnvGraph:
        return EnvGraph(self._db.select_graph(key), key, self._timeout_s)

    def env(self, name: str) -> EnvGraph:
        return self._select(f"env:{name}")

    def scratch(self, incident_id: str) -> EnvGraph:
        return self._select(f"scratch:{incident_id}")

    def kb(self) -> EnvGraph:
        return self._select(KB_GRAPH)

    def ping(self) -> bool:
        try:
            return bool(self._db.connection.ping())
        except Exception:
            return False
