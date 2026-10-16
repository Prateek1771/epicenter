// saturated caller (phase 9, flip-commerce cpu-saturation): an overloaded API's client spans inflate the latency of
// the datastore they measure. API_SELF / API_CHILD are filled in per case by the test.
//
//   web/GET / -> api/List -> db/Find   (db is a datastore; its latency is only ever measured inside api/List)
//   saturated: api/List latency self x40 child x10   -> db/Find is refuted as a victim of its caller, api/List wins
//   slow db:   api/List latency self x1.1 child x10  -> the time really went to db/Find, db/Find wins

CREATE
  (web:Service {name: 'web', kind: 'proxy'}), (api:Service {name: 'api', kind: 'app'}),
  (db:Service {name: 'db', kind: 'datastore'}),
  (w:Operation {id: 'web/GET /', name: 'GET /'}), (a:Operation {id: 'api/List', name: 'List'}),
  (d:Operation {id: 'db/Find', name: 'Find'}),
  (web)-[:HAS_OP]->(w), (api)-[:HAS_OP]->(a), (db)-[:HAS_OP]->(d),
  (w)-[:CALLS {rps: 20.0, p95_ms: 60.0, err_rate: 0.0}]->(a),
  (a)-[:CALLS {rps: 20.0, p95_ms: 20.0, err_rate: 0.0}]->(d),
  (:Anomaly {id: 'an-inc-s-1', incident: 'inc-s', kind: 'latency', onset: 100, score: 0.95, detector: 'short',
             self_ratio: 1.0, child_ratio: 30.0})-[:ON]->(w),
  (:Anomaly {id: 'an-inc-s-2', incident: 'inc-s', kind: 'latency', onset: 100, score: 1.0, detector: 'short',
             self_ratio: API_SELF, child_ratio: API_CHILD})-[:ON]->(a),
  (:Anomaly {id: 'an-inc-s-3', incident: 'inc-s', kind: 'latency', onset: 100, score: 1.0, detector: 'short',
             self_ratio: 19.0, child_ratio: 0.0})-[:ON]->(d),
  (:Incident {id: 'inc-s', status: 'open', symptom: 'web/GET /', opened_at: 160, weights_version: '2026-10-16.v3'});
