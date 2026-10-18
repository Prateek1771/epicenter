#!/bin/sh
# One container, four processes: FalkorDB, the API, the web app, and Caddy in front on :7860.
# State is ephemeral: a restart starts from empty graphs; the samples in examples/samples replay on demand.
set -e

PW=$(head -c 24 /dev/urandom | od -An -tx1 | tr -d ' \n')   # a fresh password per boot, never stored

redis-server --bind 127.0.0.1 --port 6379 --requirepass "$PW" --dir /app/data/redis --save "" --appendonly no \
  --loadmodule /opt/falkordb/falkordb.so THREAD_COUNT 2 TIMEOUT_MAX 30000 &
until redis-cli -a "$PW" --no-auth-warning ping >/dev/null 2>&1; do sleep 0.5; done

export FALKORDB_URL="redis://:${PW}@127.0.0.1:6379"
export WEB_ORIGIN="${PUBLIC_URL:-http://localhost:7860}"
cd /app && uvicorn api.main:app --host 127.0.0.1 --port 8000 &
cd /app/web && PORT=3000 HOSTNAME=127.0.0.1 node server.js &

exec caddy run --config /app/deploy/Caddyfile --adapter caddyfile
