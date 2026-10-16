// multi_fault: two independent faults behind one alert (LLD §12 "Multi-fault").
//
//   web/GET / -> api/Orders -> db/Query        db/Query errors @100 (fault 1) -> api/Orders @110 -> web/GET / @120
//   web/GET / -> search/Find -> cache/Get      cache/Get latency @300 (fault 2) -> search/Find @310
//
// Expected: round 1 picks db/Query (explains 3 of 5); cache/Get and search/Find stay unexplained, which seeds round 2
// from cache/Get (earliest unexplained onset) -> ROOT_CAUSE {rank: 2} on cache/Get.

CREATE
  (web:Service {name: 'web', kind: 'app'}), (api:Service {name: 'api', kind: 'app'}),
  (db:Service {name: 'db', kind: 'datastore'}), (search:Service {name: 'search', kind: 'app'}),
  (cache:Service {name: 'cache', kind: 'datastore'}),
  (w:Operation {id: 'web/GET /', name: 'GET /'}), (a:Operation {id: 'api/Orders', name: 'Orders'}),
  (d:Operation {id: 'db/Query', name: 'Query'}), (s:Operation {id: 'search/Find', name: 'Find'}),
  (c:Operation {id: 'cache/Get', name: 'Get'}),
  (web)-[:HAS_OP]->(w), (api)-[:HAS_OP]->(a), (db)-[:HAS_OP]->(d), (search)-[:HAS_OP]->(s), (cache)-[:HAS_OP]->(c),
  (w)-[:CALLS {rps: 10.0, p95_ms: 50.0, err_rate: 0.3}]->(a),
  (a)-[:CALLS {rps: 10.0, p95_ms: 20.0, err_rate: 0.4}]->(d),
  (w)-[:CALLS {rps: 10.0, p95_ms: 90.0, err_rate: 0.0}]->(s),
  (s)-[:CALLS {rps: 10.0, p95_ms: 80.0, err_rate: 0.0}]->(c),
  (:Anomaly {id: 'an-inc-m-1', incident: 'inc-m', kind: 'errors', onset: 100, score: 0.95, self_ratio: 3.0,
             child_ratio: 0.1, detector: 'short'})-[:ON]->(d),
  (:Anomaly {id: 'an-inc-m-2', incident: 'inc-m', kind: 'errors', onset: 110, score: 0.85, self_ratio: 0.3,
             child_ratio: 2.5, detector: 'short'})-[:ON]->(a),
  (:Anomaly {id: 'an-inc-m-3', incident: 'inc-m', kind: 'errors', onset: 120, score: 0.80, self_ratio: 0.2,
             child_ratio: 3.0, detector: 'short'})-[:ON]->(w),
  (:Anomaly {id: 'an-inc-m-4', incident: 'inc-m', kind: 'latency', onset: 300, score: 0.90, self_ratio: 4.0,
             child_ratio: 0.1, detector: 'short'})-[:ON]->(c),
  (:Anomaly {id: 'an-inc-m-5', incident: 'inc-m', kind: 'latency', onset: 310, score: 0.85, self_ratio: 0.3,
             child_ratio: 2.5, detector: 'short'})-[:ON]->(s),
  (:Incident {id: 'inc-m', status: 'open', symptom: 'web/GET /', opened_at: 125, weights_version: '2026-10-15.v2'});
