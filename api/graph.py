"""The only module that talks to FalkorDB (AGENTS.md rule 2).

Callers pass a query id from QUERIES plus parameters, never Cypher text. Every call is timed, logged and fed into a
per-query ring buffer that /health reports as p50/p95.
"""

import json
import logging
import time
from collections import defaultdict, deque
from functools import lru_cache
from pathlib import Path

from falkordb import FalkorDB
from redis.exceptions import ConnectionError as RedisConnectionError
from redis.exceptions import ResponseError
from redis.exceptions import TimeoutError as RedisTimeoutError

from api.config import get_settings

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
        MERGE (c)-[:CHANGED {ts: $ts}]->(s)
        RETURN c.id AS id""",
    # Batched forms for ingest (one round trip per tick; rows sorted by the caller)
    "U1_batch": """
        UNWIND $rows AS r
        MERGE (cs:Service {name: r.caller_svc}) ON CREATE SET cs.kind = r.caller_kind
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
    # Replays never delete anomalies: the previous ingest is re-keyed "<inc>@i<k>" so every reader (which filters
    # incident: $inc) sees only the current one, while old diagnosis runs keep their ABOUT edges.
    "next_ingest": """
        MATCH (i:Incident {id: $inc})
        WITH i, coalesce(i.ingest, 0) AS k
        SET i.ingest = k + 1
        RETURN k AS retired, i.ingest AS ingest""",
    "retire_anomalies": """
        MATCH (a:Anomaly {incident: $inc})
        SET a.id = a.id + $suffix, a.incident = $inc + $suffix""",
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
        MATCH (past)-[rc:ROOT_CAUSE]->(:Hypothesis)-[:BLAMES]->(cause)
        WHERE rc.run = past.run
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
    # --- Diagnosis (phase 3). Each diagnosis is a kept, numbered run; readers use Incident.run. ---
    "next_run": """
        MATCH (i:Incident {id: $inc})
        SET i.run = coalesce(i.run, 0) + 1, i.status = 'diagnosing'
        RETURN i.run AS run, i.symptom AS symptom, i.opened_at AS opened_at, coalesce(i.ingest, 1) AS ingest""",
    "op_anomalies": """
        MATCH (a:Anomaly {incident: $inc})-[:ON]->(o:Operation {id: $op})
        RETURN min(a.onset) AS onset, max(a.score) AS strength, collect(DISTINCT a.kind) AS kinds,
               collect(a.id) AS anomalies""",
    # Writes below MERGE on ids: a step re-run after a crash (agents/flow.py resume) never duplicates nodes.
    "H_create": """
        MATCH (i:Incident {id: $inc})
        UNWIND $rows AS r
        MATCH (o:Operation {id: r.op})
        MERGE (h:Hypothesis {id: r.id})
        ON CREATE SET h.run = $run, h.ingest = $ingest, h.round = r.round, h.status = 'open', h.hops = r.hops,
                      h.onset = r.onset, h.kinds = r.kinds, h.strength = r.strength, h.seed = r.seed,
                      h.scope = r.scope
        MERGE (i)-[:HAS_HYPOTHESIS]->(h)
        MERGE (h)-[:BLAMES]->(o)""",
    "hypothesis": """
        MATCH (h:Hypothesis {id: $id})-[:BLAMES]->(o:Operation)
        RETURN h.id AS id, o.id AS op, h.run AS run, h.round AS round, h.hops AS hops, h.onset AS onset,
               h.kinds AS kinds, h.strength AS strength, h.seed AS seed, h.scope AS scope, h.status AS status,
               h.facts AS facts, h.score AS score, h.score_parts AS score_parts""",
    "round_hypotheses": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:BLAMES]->(o:Operation)
        WHERE h.run = $run AND h.round = $round
        RETURN h.id AS id, o.id AS op, h.hops AS hops, h.onset AS onset, h.kinds AS kinds, h.strength AS strength,
               h.status AS status, h.facts AS facts, h.score AS score
        ORDER BY id""",
    # Relationship types can't be parameters, hence one query per direction
    "E_support": """
        UNWIND $rows AS r
        MATCH (h:Hypothesis {id: r.hyp})
        MERGE (e:Evidence {id: r.id})
        ON CREATE SET e.kind = r.kind, e.summary = r.summary, e.path = r.path, e.value = r.value
        MERGE (h)-[:SUPPORTED_BY {by: r.by}]->(e)
        WITH e, r
        UNWIND r.anomalies AS aid
        MATCH (a:Anomaly {incident: $inc, id: aid})
        MERGE (e)-[:ABOUT]->(a)""",
    "E_refute": """
        UNWIND $rows AS r
        MATCH (h:Hypothesis {id: r.hyp})
        MERGE (e:Evidence {id: r.id})
        ON CREATE SET e.kind = r.kind, e.summary = r.summary, e.path = r.path, e.value = r.value
        MERGE (h)-[:REFUTED_BY {by: r.by}]->(e)
        WITH e, r
        UNWIND r.anomalies AS aid
        MATCH (a:Anomaly {incident: $inc, id: aid})
        MERGE (e)-[:ABOUT]->(a)""",
    "E_about_change": """
        UNWIND $rows AS r
        MATCH (e:Evidence {id: r.evidence})
        MATCH (c:Change {id: r.change})
        MERGE (e)-[:ABOUT]->(c)""",
    "H_facts": """
        MATCH (h:Hypothesis {id: $id})
        SET h.status = $status, h.facts = $facts""",
    "H_score": """
        UNWIND $rows AS r
        MATCH (h:Hypothesis {id: r.id})
        SET h.score = r.score, h.score_parts = r.score_parts""",
    "H_status": """
        MATCH (h:Hypothesis {id: $id})
        SET h.status = $status""",
    "H_prune": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)
        WHERE h.run = $run AND h.status IN ['supported', 'inconclusive']
        SET h.status = 'pruned'
        RETURN h.id AS id
        ORDER BY id""",
    "root_cause": """
        MATCH (i:Incident {id: $inc})
        MATCH (h:Hypothesis {id: $hyp})
        MERGE (i)-[rc:ROOT_CAUSE {rank: $rank, run: $run}]->(h)
        ON CREATE SET rc.ingest = $ingest, rc.confidence = $confidence, rc.weights_version = $wv, rc.ts = $ts
        SET h.status = 'confirmed'
        FOREACH (_ IN CASE WHEN $rank = 1 THEN [1] ELSE [] END |
          SET i.status = 'diagnosed', i.confidence = $confidence, i.weights_version = $wv, i.summary = null)""",
    "run_hypotheses": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:BLAMES]->(o:Operation)
        WHERE h.run = $run
        OPTIONAL MATCH (h)-[r:SUPPORTED_BY|REFUTED_BY]->(e:Evidence)
        WITH h, o, e, r ORDER BY e.id
        RETURN h.id AS id, o.id AS op, h.status AS status, h.hops AS hops, h.onset AS onset, h.score AS score,
               h.score_parts AS score_parts,
               [x IN collect([type(r), e.kind, e.summary]) WHERE x[0] IS NOT NULL] AS evidence
        ORDER BY id""",
    # --- Fault Simulator (phase 4, LLD §7) ---
    "rules": """
        MATCH (r:Rule)
        RETURN r.id AS id, r.cause_kinds AS cause_kinds, r.symptom_kind AS symptom_kind, r.direction AS direction,
               r.p AS p, r.delay_s_max AS delay_s_max, r.service_kind AS service_kind, r.version AS version
        ORDER BY id""",
    "op_info": """
        UNWIND $ops AS x
        MATCH (s:Service)-[:HAS_OP]->(o:Operation {id: x})
        OPTIONAL MATCH ()-[c:CALLS]->(o)
        RETURN o.id AS op, s.kind AS service_kind, sum(c.rps) AS in_rps
        ORDER BY op""",
    "observed": """
        MATCH (a:Anomaly {incident: $inc})-[:ON]->(o:Operation)
        RETURN o.id AS op, collect(DISTINCT a.kind) AS kinds, min(a.onset) AS onset, max(a.score) AS score,
               collect(a.id) AS anomalies
        ORDER BY op""",
    "service_ops": "MATCH (:Service {name: $svc})-[:HAS_OP]->(o:Operation) RETURN o.id AS op ORDER BY op",
    "op_owners": """
        UNWIND $ops AS x
        MATCH (s:Service)-[:HAS_OP]->(o:Operation {id: x})
        OPTIONAL MATCH (s)-[:OWNED_BY]->(t:Team)
        RETURN o.id AS op, s.name AS service, t.name AS team
        ORDER BY op""",
    "save_simulation": """
        CREATE (sim:Simulation {id: $id, target: $target, kind: $kind, ts: $ts, rules_version: $rules_version})
        WITH sim
        UNWIND $rows AS r
        MATCH (o:Operation {id: r.op})
        CREATE (sim)-[:PREDICTS {p: r.p, hops: r.hops, kind: r.kind}]->(o)""",
    "simulation_predictions": """
        MATCH (:Simulation {id: $id})-[p:PREDICTS]->(o:Operation)
        RETURN o.id AS op, p.kind AS kind, p.p AS p, p.hops AS hops
        ORDER BY hops, op, kind""",
    "incident_no_root_cause": """
        MATCH (i:Incident {id: $inc})
        SET i.status = 'no_root_cause', i.summary = $summary, i.confidence = null, i.weights_version = $wv""",
    "footprint_values": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:SUPPORTED_BY|REFUTED_BY]->(e:Evidence)
        WHERE h.run = $run AND e.kind = 'footprint'
        MATCH (h)-[:BLAMES]->(o:Operation)
        RETURN h.id AS hypothesis, o.id AS op, e.value AS value
        ORDER BY hypothesis""",
    "run_rounds": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)
        WHERE h.run = $run
        RETURN DISTINCT h.round AS round
        ORDER BY round""",
    # why_not tool: the service's hypotheses in the incident's current run, with all their evidence
    "service_hypotheses": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:BLAMES]->(o:Operation)
              <-[:HAS_OP]-(:Service {name: $svc})
        WHERE h.run = i.run
        OPTIONAL MATCH (h)-[r:SUPPORTED_BY|REFUTED_BY]->(e:Evidence)
        WITH h, o, r, e ORDER BY e.id
        RETURN h.id AS id, o.id AS op, h.status AS status, h.score AS score, h.facts AS facts,
               [x IN collect({rel: type(r), id: e.id, kind: e.kind, summary: e.summary, path: e.path})
                WHERE x.id IS NOT NULL] AS evidence
        ORDER BY id""",
    "service_anomalies": """
        MATCH (:Service {name: $svc})-[:HAS_OP]->(o:Operation)
        OPTIONAL MATCH (a:Anomaly {incident: $inc})-[:ON]->(o)
        RETURN count(a) AS n""",
    "run_evidence_ids": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[r:SUPPORTED_BY|REFUTED_BY]->(e:Evidence)
        WHERE h.run = $run
        RETURN h.id AS hypothesis, e.id AS evidence, r.by AS by
        ORDER BY evidence""",
    "incident_signature": "MATCH (i:Incident {id: $inc}) RETURN i.signature AS signature",
    "incident": """
        MATCH (i:Incident {id: $inc})
        OPTIONAL MATCH (i)-[:TRIGGERED_BY]->(al:Alert)
        RETURN i.status AS status, i.summary AS summary, i.run AS run, i.ingest AS ingest,
               i.confidence AS confidence, i.symptom AS symptom, i.opened_at AS opened_at, i.gaps AS gaps,
               i.weights_version AS weights_version, coalesce(sum(al.count), 0) AS alert_count""",
    "root_causes": """
        MATCH (i:Incident {id: $inc})-[r:ROOT_CAUSE]->(h:Hypothesis)-[:BLAMES]->(o:Operation)
        WHERE r.run = i.run
        RETURN r.rank AS rank, o.id AS op, h.id AS hypothesis, r.confidence AS confidence
        ORDER BY rank""",
    # Anomalies one run's evidence cites; for an older run they may be retired ("<inc>@i<k>") ingests
    "run_evidence_about": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:SUPPORTED_BY|REFUTED_BY]->(e:Evidence)
              -[:ABOUT]->(a:Anomaly)
        WHERE h.run = $run
        RETURN e.id AS evidence, a.id AS anomaly, a.incident AS anomaly_incident
        ORDER BY evidence, anomaly""",
    "run_ingests": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)
        RETURN DISTINCT h.run AS run, h.ingest AS ingest
        ORDER BY run""",
    # --- Tool queries (LLD §2.3) ---
    "blast_radius": """
        MATCH (s:Service {name: $svc})-[:HAS_OP]->(o)
        MATCH p = (caller:Operation)-[:CALLS*1..6]->(o)
        MATCH (cs:Service)-[:HAS_OP]->(caller)
        OPTIONAL MATCH (cs)-[:OWNED_BY]->(t:Team)
        RETURN cs.name AS service, caller.id AS op, min(length(p)) AS hops, t.name AS team
        ORDER BY hops, op""",
    "why_not": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:BLAMES]->(o:Operation)
              <-[:HAS_OP]-(:Service {name: $svc})
        WHERE h.run = i.run
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
        OPTIONAL MATCH (f:Person)-[:FIXED]->(fi:Incident)-[rc:ROOT_CAUSE]->(:Hypothesis)-[:BLAMES]->(:Operation)
                       <-[:HAS_OP]-(s)
        WHERE rc.run = fi.run
        WITH s, members, collect(f) AS fixers
        OPTIONAL MATCH (a:Person)-[:AUTHORED]->(:Change)-[:CHANGED]->(s)
        WITH members, fixers, collect(a) AS authors
        UNWIND members + fixers + authors AS p
        RETURN p.handle AS handle, p.name AS name, count(*) AS score
        ORDER BY score DESC, handle""",
    # --- REST API (phase 6, API.md) ---
    # An alert re-sent with the same id lands on the incident it already opened
    "alert_incident": """
        MATCH (i:Incident)-[:TRIGGERED_BY]->(:Alert {id: $id})
        RETURN i.id AS id, i.status AS status""",
    # Join window: an unresolved incident on the same symptom opened within ±$window_s of the alert
    "alert_find_open": """
        MATCH (i:Incident {symptom: $symptom})
        WHERE i.status <> 'resolved' AND i.opened_at >= $ts - $window_s AND i.opened_at <= $ts + $window_s
        RETURN i.id AS id, i.status AS status
        ORDER BY i.opened_at DESC, id
        LIMIT 1""",
    "alert_open_incident": """
        MERGE (i:Incident {id: $id})
        ON CREATE SET i.status = 'open', i.symptom = $symptom, i.opened_at = $opened_at, i.gaps = [],
                      i.weights_version = $weights_version
        RETURN i.status AS status""",
    "alert_upsert": """
        MATCH (i:Incident {id: $inc})
        MERGE (a:Alert {id: $id})
        ON CREATE SET a.starts_at = $starts_at, a.labels = $labels, a.count = 0
        SET a.count = a.count + 1
        MERGE (i)-[:TRIGGERED_BY]->(a)
        WITH i, a
        OPTIONAL MATCH (o:Operation {id: $symptom})
        FOREACH (_ IN CASE WHEN o IS NULL THEN [] ELSE [1] END | MERGE (a)-[:FIRED_ON]->(o))
        WITH DISTINCT i
        MATCH (i)-[:TRIGGERED_BY]->(x:Alert)
        RETURN sum(x.count) AS alert_count""",
    # Cursor = (opened_at, id) of the last row, newest first; $limit is page size + 1 to know if there is a next page
    "incidents_page": """
        MATCH (i:Incident)
        WITH i, coalesce(i.opened_at, 0) AS opened_at
        WHERE ($status IS NULL OR i.status = $status)
          AND ($c_ts IS NULL OR opened_at < $c_ts OR (opened_at = $c_ts AND i.id < $c_id))
        OPTIONAL MATCH (i)-[rc:ROOT_CAUSE {rank: 1}]->(:Hypothesis)-[:BLAMES]->(o:Operation)<-[:HAS_OP]-(s:Service)
        WHERE rc.run = i.run
        WITH i, opened_at, rc, o, s
        WHERE $cause IS NULL OR s.name = $cause
        RETURN i.id AS id, i.status AS status, i.symptom AS symptom, o.id AS root_cause, rc.confidence AS confidence,
               opened_at
        ORDER BY opened_at DESC, id DESC
        LIMIT $limit""",
    "hypothesis_evidence": """
        MATCH (h:Hypothesis {id: $id})-[r:SUPPORTED_BY|REFUTED_BY]->(e:Evidence)
        OPTIONAL MATCH (e)-[:ABOUT]->(a:Anomaly)
        WITH r, e, collect(a.ref) AS refs
        RETURN e.id AS id, e.kind AS kind, type(r) AS rel, e.summary AS summary, e.path AS path, e.value AS value,
               head(refs) AS ref
        ORDER BY id""",
    # Numbered in the same write as the count, and FalkorDB serializes writes per graph: no duplicate ids
    "decision_add": """
        MATCH (i:Incident {id: $inc})
        OPTIONAL MATCH (i)-[:HAS_DECISION]->(d:Decision)
        WITH i, count(d) + 1 AS n
        CREATE (i)-[:HAS_DECISION]->(x:Decision {id: $inc + ':d-' + toString(n), by: $by, text: $text, ts: $ts})
        RETURN x.id AS id, n""",
    "incident_resolve": """
        MATCH (i:Incident {id: $inc})
        SET i.status = 'resolved', i.resolved_at = $ts
        MERGE (p:Person {handle: $by})
        MERGE (p)-[:FIXED]->(i)""",
    # Action ids are incident-scoped (`<incident>:a-<n>`), so the id alone finds the incident's action
    "action": """
        MATCH (a:Action {id: $id})
        OPTIONAL MATCH (a)-[f:FROM]->(rb:Runbook)
        RETURN a.id AS id, f.step AS step, rb.id AS runbook, rb.success AS success""",
    "action_resolve": """
        MATCH (i:Incident {id: $inc}), (a:Action {id: $id})
        SET a.status = 'done'
        MERGE (i)-[:RESOLVED_BY]->(a)""",
    "runbook_success": "MATCH (r:Runbook {id: $id}) SET r.success = $success",
    "service_exists": "MATCH (s:Service {name: $svc}) RETURN s.name AS name",
    # Undirected CALLS neighbourhood of the start operations, bounded at 3 hops, with the calls among the result
    "subgraph": """
        UNWIND $starts AS sid
        MATCH (s:Operation {id: sid})
        MATCH p = (s)-[:CALLS*0..3]-(n:Operation)
        WHERE length(p) <= $hops
        WITH collect(DISTINCT n) AS ns
        UNWIND ns AS x
        MATCH (sv:Service)-[:HAS_OP]->(x)
        OPTIONAL MATCH (x)-[c:CALLS]->(y:Operation)
        WHERE y IN ns
        WITH x, sv, c, y ORDER BY y.id
        RETURN x.id AS id, sv.name AS service, sv.kind AS service_kind,
               [z IN collect(CASE WHEN y IS NULL THEN NULL
                                  ELSE {to: y.id, rps: c.rps, p95_ms: c.p95_ms, err_rate: c.err_rate} END)
                WHERE z IS NOT NULL] AS calls
        ORDER BY id""",
    "subgraph_anomalies": """
        UNWIND $ops AS x
        MATCH (a:Anomaly {incident: $inc})-[:ON]->(o:Operation {id: x})
        RETURN a.id AS id, o.id AS op, a.kind AS kind, a.onset AS onset, a.score AS score
        ORDER BY id""",
    "subgraph_hypotheses": """
        MATCH (i:Incident {id: $inc})-[:HAS_HYPOTHESIS]->(h:Hypothesis)-[:BLAMES]->(o:Operation)
        WHERE h.run = i.run AND o.id IN $ops
        RETURN h.id AS id, o.id AS op, h.status AS status, h.score AS score
        ORDER BY id""",
    "service_past_incidents": """
        MATCH (i:Incident)-[rc:ROOT_CAUSE]->(:Hypothesis)-[:BLAMES]->(:Operation)<-[:HAS_OP]-(:Service {name: $svc})
        WHERE rc.run = i.run
        RETURN DISTINCT i.id AS id
        ORDER BY id""",
    # --- Seed (GRAPH_SCHEMA §5, LLD §7.1) ---
    "idx_service": "CREATE INDEX FOR (s:Service) ON (s.name)",
    "idx_operation": "CREATE INDEX FOR (o:Operation) ON (o.id)",
    "idx_anomaly": "CREATE INDEX FOR (a:Anomaly) ON (a.incident)",
    "idx_change": "CREATE INDEX FOR (c:Change) ON (c.ts)",
    "idx_change_id": "CREATE INDEX FOR (c:Change) ON (c.id)",
    "idx_evidence": "CREATE INDEX FOR (e:Evidence) ON (e.id)",
    "idx_incident": "CREATE INDEX FOR (i:Incident) ON (i.id)",
    "idx_hypothesis": "CREATE INDEX FOR (h:Hypothesis) ON (h.id)",
    "idx_person": "CREATE INDEX FOR (p:Person) ON (p.handle)",
    "idx_simulation": "CREATE INDEX FOR (s:Simulation) ON (s.id)",
    "idx_signal": "CREATE INDEX FOR (s:Signal) ON (s.id)",
    "idx_signal_text": "CALL db.idx.fulltext.createNodeIndex('Signal', 'text')",
    "idx_incident_signature": "CREATE VECTOR INDEX FOR (i:Incident) ON (i.signature) "
    "OPTIONS {dimension: 64, similarityFunction: 'cosine'}",
    "idx_rule": "CREATE INDEX FOR (r:Rule) ON (r.id)",
    "idx_alert": "CREATE INDEX FOR (a:Alert) ON (a.id)",
    "idx_incident_symptom": "CREATE INDEX FOR (i:Incident) ON (i.symptom)",
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


# Incident event streams (LLD §9): one Redis Stream per `<graph key>:<incident>` in FalkorDB's own Redis. INCR and XADD
# run in one script, so `seq` is gap-free, monotonic across API restarts, and doubles as the stream id `0-<seq>`.
_PUBLISH_EVENT = """
local seq = redis.call('INCR', KEYS[1])
redis.call('XADD', KEYS[2], 'MAXLEN', '~', ARGV[3], '0-' .. seq, 'event', ARGV[1], 'data', ARGV[2])
return seq"""
EVENTS_KEEP = 10000  # per incident; older events are trimmed (a full run is ~600)


def _s(x) -> str:
    return x.decode() if isinstance(x, bytes) else x


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

    def env_names(self) -> list[str]:
        """Environments that have a graph (`env:<name>`), sorted."""
        try:
            return sorted(k[4:] for k in self._db.list_graphs() if k.startswith("env:"))
        except (RedisConnectionError, RedisTimeoutError) as e:
            raise GraphUnavailable(str(e)) from e

    def _redis(self, fn):
        try:
            return fn(self._db.connection)
        except (RedisConnectionError, RedisTimeoutError) as e:
            raise GraphUnavailable(str(e)) from e

    def publish_event(self, key: str, event: str, data: str) -> int:
        """Append one event to the stream of `key` (`env:<name>:<incident>`); returns its seq."""
        return int(
            self._redis(lambda c: c.eval(_PUBLISH_EVENT, 2, f"seq:{key}", f"events:{key}", event, data, EVENTS_KEEP))
        )

    def read_events(self, key: str, after_seq: int = 0, block_ms: int = 0) -> list[dict]:
        """Events of `key` after `after_seq`, oldest first. With `block_ms`, waits up to that long for new ones
        (keep it under the socket timeout, query_timeout_s)."""
        stream = f"events:{key}"

        def read(c):
            if block_ms:
                res = c.xread({stream: f"0-{after_seq}"}, block=block_ms)
                return res[0][1] if res else []
            return c.xrange(stream, min=f"(0-{after_seq}")

        out = []
        for i, f in self._redis(read):
            f = {_s(k): _s(v) for k, v in f.items()}
            out.append({"seq": int(_s(i).split("-")[1]), "event": f["event"], "data": json.loads(f["data"])})
        return out

    def ping(self) -> bool:
        try:
            return bool(self._db.connection.ping())
        except Exception:
            return False


@lru_cache
def get_graph() -> Graph:
    """The process-wide client (agents, tools, events)."""
    s = get_settings()
    return Graph(s.falkordb_url, s.query_timeout_s)
