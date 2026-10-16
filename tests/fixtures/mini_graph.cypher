// mini_graph: 8 operations, 5 services, one incident (inc-1) whose root cause is payment/Charge (flag change ch-1).
// Loaded into env:test by tests/conftest.py. Statements are separated by `;`.
//
// CALLS (rps):  frontend/GET /checkout -> checkout/PlaceOrder (10) -> payment/Charge (10)
//               checkout/PlaceOrder -> cart/GetCart (10), -> checkout/GetQuote (5), -> payment/Refund (0, no traffic)
//               frontend/GET /cart -> cart/GetCart (10);  cart/GetCart -> redis/GET (20)
// inc-1 anomalies: Charge errors @100 (self-caused), PlaceOrder errors @110 (victim), GET /checkout errors @120,
//                  GetCart latency @200 (weak, unrelated). Change ch-1 (flag, payment) @60, authored by alice.
//
// Expected answers (tests/test_graph.py):
//   Q1 symptom=frontend/GET /checkout, inc=inc-1 -> Charge (hops 2, onset 100), PlaceOrder (1, 110), GetCart (2, 200)
//   Q2 cand=payment/Charge  -> path [GET /checkout, PlaceOrder, Charge], onsets [120, 110, 100]
//   Q3 cand=payment/Charge  -> changes [ch-1];  cand=checkout/PlaceOrder -> changes []
//   Q4a inc-1               -> GET /checkout->PlaceOrder, PlaceOrder->Charge, PlaceOrder->GetCart
//   Q5 sig=e0, inc=inc-1    -> inc-0 (cause payment/Charge, fix "disable flag paymentFailure"), then inc-00
//   Q6 cand=payment/Charge  -> PlaceOrder @1, GET /checkout @2;  cand=payment/Refund -> none (rps 0)
//   blast_radius redis      -> GetCart @1, GET /cart @2, PlaceOrder @2, GET /checkout @3
//   why_not inc-1 checkout  -> inc-1:h-2 refuted by inc-1:E2 (victim)
//   recent_changes payment  -> ch-1 by alice
//   who_knows payment       -> alice 2 (member + author), bob 2 (member + fixed inc-0), carol 1 (fixed inc-0)

CREATE
  (fe:Service {name: 'frontend', kind: 'app', last_seen: 1000}),
  (co:Service {name: 'checkout', kind: 'app', last_seen: 1000}),
  (pa:Service {name: 'payment', kind: 'app', last_seen: 1000}),
  (ca:Service {name: 'cart', kind: 'app', last_seen: 1000}),
  (re:Service {name: 'redis', kind: 'datastore', last_seen: 1000}),

  (f1:Operation {id: 'frontend/GET /checkout', name: 'GET /checkout', last_seen: 1000}),
  (f2:Operation {id: 'frontend/GET /cart', name: 'GET /cart', last_seen: 1000}),
  (c1:Operation {id: 'checkout/PlaceOrder', name: 'PlaceOrder', last_seen: 1000}),
  (c2:Operation {id: 'checkout/GetQuote', name: 'GetQuote', last_seen: 1000}),
  (p1:Operation {id: 'payment/Charge', name: 'Charge', last_seen: 1000}),
  (p2:Operation {id: 'payment/Refund', name: 'Refund', last_seen: 1000}),
  (k1:Operation {id: 'cart/GetCart', name: 'GetCart', last_seen: 1000}),
  (r1:Operation {id: 'redis/GET', name: 'GET', last_seen: 1000}),

  (fe)-[:HAS_OP]->(f1), (fe)-[:HAS_OP]->(f2), (co)-[:HAS_OP]->(c1), (co)-[:HAS_OP]->(c2),
  (pa)-[:HAS_OP]->(p1), (pa)-[:HAS_OP]->(p2), (ca)-[:HAS_OP]->(k1), (re)-[:HAS_OP]->(r1),

  (f1)-[:CALLS {rps: 10.0, p95_ms: 900.0, err_rate: 0.30, last_seen: 1000}]->(c1),
  (c1)-[:CALLS {rps: 10.0, p95_ms: 800.0, err_rate: 0.35, last_seen: 1000}]->(p1),
  (c1)-[:CALLS {rps: 10.0, p95_ms: 40.0, err_rate: 0.00, last_seen: 1000}]->(k1),
  (c1)-[:CALLS {rps: 5.0, p95_ms: 20.0, err_rate: 0.00, last_seen: 1000}]->(c2),
  (c1)-[:CALLS {rps: 0.0, p95_ms: 0.0, err_rate: 0.00, last_seen: 1000}]->(p2),
  (f2)-[:CALLS {rps: 10.0, p95_ms: 50.0, err_rate: 0.00, last_seen: 1000}]->(k1),
  (k1)-[:CALLS {rps: 20.0, p95_ms: 5.0, err_rate: 0.00, last_seen: 1000}]->(r1),

  (:Anomaly {id: 'an-inc-1-1', incident: 'inc-1', kind: 'errors', onset: 100, score: 0.95,
             self_ratio: 3.0, child_ratio: 0.2, detector: 'short', ref: 'promql:errors{op="Charge"}'})-[:ON]->(p1),
  (:Anomaly {id: 'an-inc-1-2', incident: 'inc-1', kind: 'errors', onset: 110, score: 0.80,
             self_ratio: 0.3, child_ratio: 2.5, detector: 'short'})-[:ON]->(c1),
  (:Anomaly {id: 'an-inc-1-3', incident: 'inc-1', kind: 'errors', onset: 120, score: 0.70,
             self_ratio: 0.2, child_ratio: 3.0, detector: 'short'})-[:ON]->(f1),
  (:Anomaly {id: 'an-inc-1-4', incident: 'inc-1', kind: 'latency', onset: 200, score: 0.40,
             self_ratio: 1.1, child_ratio: 0.9, detector: 'short'})-[:ON]->(k1),

  (ch:Change {id: 'ch-1', type: 'flag', ts: 60, summary: 'flag paymentFailure -> on', ref: 'flagd:1'}),
  (ch)-[:CHANGED {ts: 60}]->(pa),

  (web:Team {name: 'web'}), (pay:Team {name: 'payments'}), (plat:Team {name: 'platform'}),
  (fe)-[:OWNED_BY]->(web), (co)-[:OWNED_BY]->(pay), (pa)-[:OWNED_BY]->(pay),
  (ca)-[:OWNED_BY]->(plat), (re)-[:OWNED_BY]->(plat),
  (alice:Person {handle: 'alice', name: 'Alice'}), (bob:Person {handle: 'bob', name: 'Bob'}),
  (carol:Person {handle: 'carol', name: 'Carol'}),
  (alice)-[:MEMBER_OF]->(pay), (bob)-[:MEMBER_OF]->(pay), (carol)-[:MEMBER_OF]->(plat),
  (alice)-[:AUTHORED]->(ch),

  // the open incident and one refuted hypothesis (ids scoped per incident, Q-a)
  (i1:Incident {id: 'inc-1', status: 'diagnosing', symptom: 'frontend/GET /checkout', opened_at: 130,
                weights_version: '2026-10-15.v2'}),
  (h2:Hypothesis {id: 'inc-1:h-2', status: 'refuted', hops: 1, onset: 110}),
  (e2:Evidence {id: 'inc-1:E2', kind: 'victim', summary: 'checkout/PlaceOrder is a victim: its callee explains it',
                path: ['checkout/PlaceOrder', 'payment/Charge']}),
  (i1)-[:HAS_HYPOTHESIS]->(h2), (h2)-[:BLAMES]->(c1), (h2)-[:REFUTED_BY {by: 'skeptic'}]->(e2),

  // past resolved incidents for memory recall (Q5) and who_knows
  (i0:Incident {id: 'inc-0', status: 'resolved', symptom: 'frontend/GET /checkout', opened_at: 10,
                weights_version: '2026-10-15.v2'}),
  (h0:Hypothesis {id: 'inc-0:h-1', status: 'confirmed', hops: 2}),
  (a0:Action {id: 'inc-0:a-1', name: 'disable flag paymentFailure', status: 'done'}),
  (i0)-[:HAS_HYPOTHESIS]->(h0), (i0)-[:ROOT_CAUSE {rank: 1}]->(h0), (h0)-[:BLAMES]->(p1), (i0)-[:RESOLVED_BY]->(a0),
  (bob)-[:FIXED]->(i0), (carol)-[:FIXED]->(i0),

  (i00:Incident {id: 'inc-00', status: 'resolved', symptom: 'frontend/GET /cart', opened_at: 5,
                 weights_version: '2026-10-15.v2'}),
  (h00:Hypothesis {id: 'inc-00:h-1', status: 'confirmed', hops: 2}),
  (i00)-[:HAS_HYPOTHESIS]->(h00), (i00)-[:ROOT_CAUSE {rank: 1}]->(h00), (h00)-[:BLAMES]->(r1);

// 64-dim signatures (ADR 0008): inc-1 and inc-0 = e0, inc-00 = mostly e1 (still within the top 5)
MATCH (i:Incident) WHERE i.id IN ['inc-1', 'inc-0']
SET i.signature = vecf32([x IN range(0, 63) | CASE WHEN x = 0 THEN 1.0 ELSE 0.0 END]);
MATCH (i:Incident {id: 'inc-00'})
SET i.signature = vecf32([x IN range(0, 63) | CASE WHEN x = 1 THEN 1.0 WHEN x = 0 THEN 0.2 ELSE 0.0 END]);
