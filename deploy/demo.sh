#!/usr/bin/env bash
# On the demo box, from /opt/epicenter (phase 11, SETUP §9): up | down | status | backup
# Secrets are generated here and live only in this box's .env (chmod 600); never in user-data, git or logs.
set -euo pipefail
cd "$(dirname "$0")/.."

COMPOSE=(docker compose -f docker-compose.yml -f deploy/compose.prod.yaml)
export DEMO_DIR=/opt/opentelemetry-demo
export FLIP_REPO=/opt/system-design-journey/season-1/2.vertical-vs-horizontal-scaling
export FAULT_RUNNER_BIND=0.0.0.0   # containers reach the host runner over docker0; still token-gated, port closed by the SG
CASES=(re2tt_ts-auth-service_cpu_2 re2tt_ts-order-service_delay_1 re2tt_ts-auth-service_cpu_1)

setenv() {  # set KEY to VALUE in .env (replace or append); values are single-quoted when they hold a `$`
  local k=$1 v=$2
  [[ $v == *'$'* ]] && v="'$v'"
  if grep -q "^$k=" .env; then
    python3 - "$k" "$v" <<'EOF'
import sys
k, v = sys.argv[1], sys.argv[2]
lines = open(".env", encoding="utf-8").read().splitlines()
open(".env", "w", encoding="utf-8").write("\n".join(f"{k}={v}" if l.startswith(k + "=") else l for l in lines) + "\n")
EOF
  else
    echo "$k=$v" >> .env
  fi
}
getenv() { grep "^$1=" .env | head -1 | cut -d= -f2- | sed "s/^'//; s/'$//; s/ *#.*//"; }

public_host() {
  local t ip
  t=$(curl -fsS -X PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 60")
  ip=$(curl -fsS -H "X-aws-ec2-metadata-token: $t" http://169.254.169.254/latest/meta-data/public-ipv4)
  echo "${ip//./-}.sslip.io"
}

make_env() {
  cp .env.example .env
  chmod 600 .env
  [ -f .env.openconnector ] || cp .env.openconnector.example .env.openconnector
  local host pw
  host=$(public_host)
  pw=$(openssl rand -hex 12)
  for k in FALKORDB_PASSWORD MCP_API_KEY FAULT_RUNNER_TOKEN; do setenv "$k" "$(openssl rand -hex 24)"; done
  read -r -s -p "OpenRouter API key (a separate key with a spend limit; empty = template explanations): " key; echo
  setenv OPENROUTER_API_KEY "$key"
  setenv EPICENTER_HOST "$host"
  setenv PUBLIC_API_URL "https://$host/api/v1"
  setenv WEB_ORIGIN "https://$host"
  setenv DEMO_USER demo
  setenv DEMO_PASSWORD_HASH "$(docker run --rm caddy:2.10.2-alpine caddy hash-password --plaintext "$pw")"
  echo "$pw" > .demo-password && chmod 600 .demo-password
}

case "${1:-}" in
up)
  [ -f .env ] || make_env
  "${COMPOSE[@]}" up -d --build
  for _ in $(seq 1 60); do curl -fsS http://127.0.0.1:8000/api/v1/health >/dev/null 2>&1 && break; sleep 3; done
  "${COMPOSE[@]}" exec -T api python -m api.smoke_falkordb
  for c in "${CASES[@]}"; do
    "${COMPOSE[@]}" exec -T api python -m api.ingest.rcaeval --case "$c" --env rcaeval-tt --download >/dev/null \
      && "${COMPOSE[@]}" exec -T api python -m api.search.causal --env rcaeval-tt --incident "rc-$c" >/dev/null \
      && echo "rcaeval-tt: rc-$c replayed and diagnosed"
  done
  python3 examples/otel-demo/run.py up
  host=$(getenv EPICENTER_HOST)
  echo
  echo "  https://$host   login: $(getenv DEMO_USER) / $(cat .demo-password 2>/dev/null || echo '(set earlier)')"
  echo "  Let the OTel Demo load run >= 10 min before the first fault (the detector's baseline)."
  ;;
down)
  python3 examples/otel-demo/run.py down || true
  python3 examples/flip-commerce/run.py down || true
  "${COMPOSE[@]}" stop   # never `down -v`: the graph is the incident history
  ;;
status)
  "${COMPOSE[@]}" ps --format '{{.Service}}\t{{.Status}}'
  curl -fsS http://127.0.0.1:8000/api/v1/health || echo "api: down"
  echo
  for e in otel-demo flip-commerce; do echo "--- $e"; python3 "examples/$e/run.py" status 2>/dev/null | head -20 || true; done
  curl -fsS -o /dev/null -w "fault runner: %{http_code}\n" http://127.0.0.1:8090/health || echo "fault runner: down"
  free -h | head -2; df -h / | tail -1
  host=$(getenv EPICENTER_HOST)
  echo | openssl s_client -connect "$host:443" -servername "$host" 2>/dev/null | openssl x509 -noout -enddate || echo "no certificate yet"
  ;;
backup)
  pw=$(getenv FALKORDB_PASSWORD)
  r() { "${COMPOSE[@]}" exec -T falkordb redis-cli -a "$pw" --no-auth-warning "$@" | tr -d '\r'; }
  t0=$(r LASTSAVE); r BGSAVE >/dev/null
  for _ in $(seq 1 60); do [ "$(r LASTSAVE)" != "$t0" ] && break; sleep 1; done
  mkdir -p backups
  out="backups/epicenter-$(date -u +%Y%m%dT%H%M%SZ).rdb"
  "${COMPOSE[@]}" cp falkordb:/var/lib/falkordb/data/dump.rdb "$out"
  echo "$out  (from the laptop: deploy/aws.sh ssh -- cat /opt/epicenter/$out > data/backups/$(basename "$out"))"
  ;;
*)
  sed -n '2,3p' "$0"; exit 2 ;;
esac
