// healthy: an alert with only weak, unrelated anomalies (LLD §12 "Healthy baseline").
//
//   web/GET / -> api/Orders -> db/Query, web/GET / -> search/Find
//   web/GET / latency 0.45 @100 (the alert), search/Find latency 0.40 @250, db/Query errors 0.35 @400
//
// Expected: nothing explains >= 50% of the symptoms and the strongest anomaly is < 0.6
// -> Incident status no_root_cause, a summary, and no ROOT_CAUSE edge.

CREATE
  (web:Service {name: 'web', kind: 'app'}), (api:Service {name: 'api', kind: 'app'}),
  (db:Service {name: 'db', kind: 'datastore'}), (search:Service {name: 'search', kind: 'app'}),
  (w:Operation {id: 'web/GET /', name: 'GET /'}), (a:Operation {id: 'api/Orders', name: 'Orders'}),
  (d:Operation {id: 'db/Query', name: 'Query'}), (s:Operation {id: 'search/Find', name: 'Find'}),
  (web)-[:HAS_OP]->(w), (api)-[:HAS_OP]->(a), (db)-[:HAS_OP]->(d), (search)-[:HAS_OP]->(s),
  (w)-[:CALLS {rps: 10.0, p95_ms: 50.0, err_rate: 0.0}]->(a),
  (a)-[:CALLS {rps: 10.0, p95_ms: 20.0, err_rate: 0.0}]->(d),
  (w)-[:CALLS {rps: 10.0, p95_ms: 30.0, err_rate: 0.0}]->(s),
  (:Anomaly {id: 'an-inc-h-1', incident: 'inc-h', kind: 'latency', onset: 100, score: 0.45, detector: 'short'})-[:ON]->(w),
  (:Anomaly {id: 'an-inc-h-2', incident: 'inc-h', kind: 'latency', onset: 250, score: 0.40, detector: 'short'})-[:ON]->(s),
  (:Anomaly {id: 'an-inc-h-3', incident: 'inc-h', kind: 'errors', onset: 400, score: 0.35, detector: 'short'})-[:ON]->(d),
  (:Incident {id: 'inc-h', status: 'open', symptom: 'web/GET /', opened_at: 105, weights_version: '2026-10-15.v2'});
