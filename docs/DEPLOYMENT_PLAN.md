# Deployment plan: Epicenter on AWS

**Status: planned and scripted, not executed.** The event demo runs locally on the presenter's laptop
([ADR 0014](adr/0014-local-event-demo.md)). This page is the plan for putting Epicenter on a public URL. The scripts
in [`deploy/`](../deploy) implement it end to end and are ready to run; they were not run against AWS for the event.

Design decisions: [ADR 0013](adr/0013-ephemeral-demo-deployment.md). Diagram and ports:
[HLD §5.3](HLD.md#53-demo-deployment-aws).

## 1. Target

| Item | Choice | Why |
|---|---|---|
| Host | one EC2 `m6i.2xlarge` (8 vCPU, 32 GB), Ubuntu 24.04, 60 GB gp3 | runs the laptop topology unchanged: Epicenter ~3 GB, OTel Demo ~6 GB, flip-commerce ~2 GB; steady CPU (no burst credits) |
| Front door | Caddy 2.10: HTTPS (Let's Encrypt) + basic auth | UI and API share one origin, so basic auth covers `fetch` and `EventSource`; `/api/*` is proxied with `flush_interval -1` so SSE arrives live |
| Name | `<elastic-ip-with-dashes>.sslip.io` | a real certificate without buying a domain; fallback: own domain or `tls internal` |
| Address | Elastic IP | the URL survives stop / start |
| Metadata | IMDSv2 required | blocks SSRF-style reads of instance metadata |
| Tags | `Project=epicenter-demo` on every resource | `destroy` finds and deletes everything by tag |

## 2. Security boundary

- **Public:** only 80 and 443 (Caddy). SSH (22) only from the presenter's current IP (`aws.sh allow-my-ip`).
- **Loopback only:** every Epicenter port (FalkorDB 6380 / 3002, falkordb-mcp 8081, API 8000, web 3001, OpenConnector
  3000), via `ports: !override` in [`deploy/compose.prod.yaml`](../deploy/compose.prod.yaml). MCP and the FalkorDB
  browser are reached over an SSH tunnel.
- **The security group is the network boundary**, because Docker bypasses `ufw` and the example environments publish
  their own ports.
- **Secrets** are generated on the box into `.env` (mode 600) by `demo.sh up`. They never go into cloud-init
  user-data, an AMI or git. The OpenRouter key is typed on the box without echo; use a separate key with a spend
  limit, revoked afterwards.
- The fault runner stays token-gated. Port 8090 is closed by the security group.

## 3. Lifecycle and cost

```bash
export AWS_PROFILE=<profile> AWS_REGION=ap-south-1             # a profile with EC2 rights
deploy/aws.sh create        # key pair, security group, Elastic IP, Ubuntu box + tools + clones; waits for /opt/READY
deploy/aws.sh ssh           # shell with tunnels for 3002 / 8000
  cd /opt/epicenter && deploy/demo.sh up       # .env, compose up behind Caddy, smoke, replays, OTel Demo; prints URL + login
  python3 syscheck.py --run --live             # rehearsal, expects tier 4
  deploy/demo.sh backup                        # BGSAVE → backups/epicenter-<utc>.rdb
deploy/aws.sh stop | start | status
deploy/aws.sh destroy       # lists everything tagged, asks y/N, deletes, checks no volume / snapshot is left
```

| State | Pays for | Roughly |
|---|---|---|
| Running | instance + EBS + public IPv4 | ~$0.40 / h |
| Stopped | EBS 60 GB + idle Elastic IP | ~$0.30 / day |
| Destroyed | nothing | $0 |

A 3-day window with ~10 running hours: under $10. Set a $20 AWS Budgets alert.

## 4. What is verified, and what isn't

| Verified locally | Not verified (nothing was deployed) |
|---|---|
| `bash -n` on `aws.sh`, `demo.sh`, `cloud-init.sh` | `aws.sh create` / `destroy` against a real account |
| `docker compose -f docker-compose.yml -f deploy/compose.prod.yaml config` | Let's Encrypt issuance on `sslip.io` (shared rate limits) |
| Caddy basic auth in front of the stack: 401 without the login, UI + API with it | the external port scan (`nmap -Pn -p 1-65535 <host>`: only 80 / 443 / 22) |
| SSE through Caddy: 101 events streamed live with `flush_interval -1` | `destroy` leaving zero tagged resources (`aws resourcegroupstaggingapi get-resources`) |
| `syscheck.py`, the selftest and the samples on the laptop | tier 4 on the EC2 box |

## 5. From demo box to production

The box is a demo environment, not production: one host, basic auth, and fault buttons for anyone with the login. To
run Epicenter for real:

1. **Identity:** OIDC at the proxy instead of basic auth; `API_KEY` for machine clients.
2. **Graph:** FalkorDB on its own instance or a managed service (`FALKORDB_URL`), with scheduled `BGSAVE` backups.
3. **API replicas** behind the proxy, after the two in-process pieces move to shared storage (AGENTS.md "Keep the API
   stateless"): a server-backed LangGraph checkpointer and a Redis lock for the "diagnosis running" set.
4. **No fault runner** and no example environments: telemetry comes from the real Jaeger / Prometheus / OpenSearch
   through the existing adapters.
5. The same compose files run on any Linux VM; Kubernetes (EKS) is the next step only when there is more than one
   tenant.

## 6. Hosted demo (Hugging Face Space)

For the event we also run a public copy on a Hugging Face Space ([ADR 0015](adr/0015-hf-space-demo.md)): one Docker
container with FalkorDB, the API and the web app behind Caddy on port 7860, built from `deploy/hf/`. Its Dockerfile
clones this repo, so a push to GitHub plus "Factory rebuild" in the Space settings redeploys it. It runs Demo 1 and
Demo 2. The live OTel shop, the fault runner and Slack / Linear stay local. Nothing persists: a restart starts from
empty graphs and the samples replay on demand. To run the same image locally:

```bash
docker build -t epicenter-hf deploy/hf && docker run -p 7860:7860 epicenter-hf    # http://localhost:7860
```
