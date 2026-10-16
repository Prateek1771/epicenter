// Steady traffic through nginx for Epicenter's flip-commerce runs: product list, product page, cart reads and
// add-to-cart writes (authenticated). Writes matter: with readPreference=primaryPreferred, Mongo faults only hurt them.
// k6 run load.js  (BASE, RATE requests/s, DURATION from env; run.py sets them)
import http from "k6/http";
import { sleep } from "k6";

const BASE = __ENV.BASE || "http://127.0.0.1:8080";
const RATE = Number(__ENV.RATE || 20);

export const options = {
  discardResponseBodies: false,
  scenarios: {
    steady: {
      executor: "constant-arrival-rate",
      rate: RATE,
      timeUnit: "1s",
      duration: __ENV.DURATION || "4h",
      preAllocatedVUs: Math.max(10, RATE),
      maxVUs: Math.max(50, RATE * 4),
    },
  },
};

export function setup() {
  const email = `epicenter-${Date.now()}@example.invalid`;
  const password = "epicenter-load-1";
  const hdr = { headers: { "Content-Type": "application/json" } };
  http.post(`${BASE}/node/users/signup`, JSON.stringify({ name: "Epicenter load", email, password }), hdr);
  // log in until the token works: a login during a Mongo election can return a token whose session was never stored
  let token = "";
  for (let i = 0; i < 30; i++) {
    const login = http.post(`${BASE}/node/users/login`, JSON.stringify({ email, password }), hdr);
    token = login.status === 200 ? login.json("accessToken") : "";
    if (token && http.get(`${BASE}/node/cart`, { headers: { Authorization: `Bearer ${token}` } }).status === 200) break;
    sleep(2);
  }
  const list = http.get(`${BASE}/node/products?limit=50`);
  const ids = list.status === 200 ? list.json("items").map((p) => p._id) : [];
  return { token, ids };
}

export default function (data) {
  const r = Math.random();
  if (r < 0.5) {
    http.get(`${BASE}/node/products?limit=20`);
  } else if (r < 0.8 && data.ids.length) {
    http.get(`${BASE}/node/products/${data.ids[Math.floor(Math.random() * data.ids.length)]}`);
  } else if (r < 0.9 || !data.ids.length) {
    http.get(`${BASE}/node/cart`, { headers: { Authorization: `Bearer ${data.token}` } });
  } else {
    const productId = data.ids[Math.floor(Math.random() * data.ids.length)];
    http.post(`${BASE}/node/cart`, JSON.stringify({ productId, qty: 1 }),
      { headers: { Authorization: `Bearer ${data.token}`, "Content-Type": "application/json" } });
  }
}
