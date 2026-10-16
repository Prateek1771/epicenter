// weak self-blame: the only anomaly is a weak latency wobble on the alert's own operation (phase 9, the OTel Demo's
// emailMemoryLeak run: checkout latency noise from before the fault). Blaming the alert's operation on that says
// nothing the alert didn't.
//
//   edge/GET / -> web/GET / -> api/Orders -> db/Query
//   web/GET / (the alert) latency 0.50 @100; its caller edge/GET / latency 0.70 @100 (stronger, but downstream)
//
// Expected: no_root_cause (LLD §7.6: the best hypothesis is the symptom itself, on a weak anomaly of its own).

CREATE
  (edge:Service {name: 'edge', kind: 'proxy'}), (web:Service {name: 'web', kind: 'app'}),
  (api:Service {name: 'api', kind: 'app'}), (db:Service {name: 'db', kind: 'datastore'}),
  (e:Operation {id: 'edge/GET /', name: 'GET /'}), (w:Operation {id: 'web/GET /', name: 'GET /'}),
  (a:Operation {id: 'api/Orders', name: 'Orders'}), (d:Operation {id: 'db/Query', name: 'Query'}),
  (edge)-[:HAS_OP]->(e), (web)-[:HAS_OP]->(w), (api)-[:HAS_OP]->(a), (db)-[:HAS_OP]->(d),
  (e)-[:CALLS {rps: 10.0, p95_ms: 60.0, err_rate: 0.0}]->(w),
  (w)-[:CALLS {rps: 10.0, p95_ms: 50.0, err_rate: 0.0}]->(a),
  (a)-[:CALLS {rps: 10.0, p95_ms: 20.0, err_rate: 0.0}]->(d),
  (:Anomaly {id: 'an-inc-w-1', incident: 'inc-w', kind: 'latency', onset: 100, score: 0.50, detector: 'short'})-[:ON]->(w),
  (:Anomaly {id: 'an-inc-w-2', incident: 'inc-w', kind: 'latency', onset: 100, score: 0.70, detector: 'short'})-[:ON]->(e),
  (:Incident {id: 'inc-w', status: 'open', symptom: 'web/GET /', opened_at: 160, weights_version: '2026-10-16.v3'});
