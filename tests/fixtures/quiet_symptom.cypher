// quiet symptom: the alert's operation shows no anomaly; one weak anomaly below it (phase 9, flip-commerce's
// absorbed Mongo failover). That anomaly "covers" itself 100%, but it explains nothing the alert saw.
//
//   web/GET / -> api/Orders -> db/Query
//   api/Orders new_template 0.31 @100 (a log line), web/GET / (the alert) nothing
//
// Expected: no_root_cause (LLD §7.6: weak anomalies and the symptom itself is fine).

CREATE
  (web:Service {name: 'web', kind: 'proxy'}), (api:Service {name: 'api', kind: 'app'}),
  (db:Service {name: 'db', kind: 'datastore'}),
  (w:Operation {id: 'web/GET /', name: 'GET /'}), (a:Operation {id: 'api/Orders', name: 'Orders'}),
  (d:Operation {id: 'db/Query', name: 'Query'}),
  (web)-[:HAS_OP]->(w), (api)-[:HAS_OP]->(a), (db)-[:HAS_OP]->(d),
  (w)-[:CALLS {rps: 10.0, p95_ms: 50.0, err_rate: 0.0}]->(a),
  (a)-[:CALLS {rps: 10.0, p95_ms: 20.0, err_rate: 0.0}]->(d),
  (:Anomaly {id: 'an-inc-q-1', incident: 'inc-q', kind: 'new_template', onset: 100, score: 0.31, detector: 'short'})-[:ON]->(a),
  (:Incident {id: 'inc-q', status: 'open', symptom: 'web/GET /', opened_at: 160, weights_version: '2026-10-15.v2'});
