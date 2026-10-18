# The hosted demo as one container: FalkorDB + API + web behind Caddy on port 7860.
# Build context is this folder; the app itself is cloned from GitHub at build time (REF = branch or tag).
# The compose stack in the repo root is unchanged; this image is for the hosted demo only (DEPLOYMENT_PLAN §6).

FROM alpine/git:2.47.2 AS src
ARG REPO=https://github.com/Prateek1771/epicenter
ARG REF=main
RUN git clone --depth 1 --branch "$REF" "$REPO" /src

FROM node:24-trixie-slim AS web
WORKDIR /web
COPY --from=src /src/web/package.json /src/web/package-lock.json ./
RUN npm ci
COPY --from=src /src/web/ ./
# Relative: the browser calls the same origin, and Caddy routes /api/* to the API
ENV NEXT_PUBLIC_API_URL=/api/v1
RUN npm run build

FROM falkordb/falkordb:v4.22.1 AS db
FROM caddy:2.10.2 AS caddy

FROM python:3.12-slim-trixie
RUN apt-get update && apt-get install -y --no-install-recommends libgomp1 libssl3t64 libstdc++6 \
    && rm -rf /var/lib/apt/lists/*
COPY --from=db /usr/local/bin/redis-server /usr/local/bin/redis-cli /usr/local/bin/
COPY --from=db /var/lib/falkordb/bin/falkordb.so /opt/falkordb/falkordb.so
COPY --from=caddy /usr/bin/caddy /usr/local/bin/caddy
COPY --from=web /usr/local/bin/node /usr/local/bin/node

WORKDIR /app
COPY --from=src /src/api/requirements.txt api/requirements.txt
RUN pip install --no-cache-dir -r api/requirements.txt
COPY --from=src /src/api/ api/
COPY --from=src /src/seed/ seed/
COPY --from=src /src/weights.json /src/weights.v1.json ./
COPY --from=src /src/examples/samples/ examples/samples/
COPY --from=src /src/examples/synthetic/ examples/synthetic/
COPY --from=web /web/.next/standalone/ /app/web/
COPY --from=web /web/.next/static/ /app/web/.next/static/
COPY --from=web /web/public/ /app/web/public/
COPY Caddyfile start.sh /app/deploy/

# runs as an unprivileged user; everything it writes lives under /app/data
RUN useradd -m -u 1000 user && mkdir -p /app/data/rcaeval /app/data/redis \
    && chmod +x /app/deploy/start.sh && chown -R user:user /app/data
USER user
ENV HOME=/home/user XDG_CONFIG_HOME=/app/data XDG_DATA_HOME=/app/data \
    ENV_NAME=synthetic LIVE_ENVS= LIVE_TICK_S=0 LIVE_SCENARIOS=false \
    SAMPLES_DIR=/app/examples/samples RCAEVAL_DIR=/app/data/rcaeval CHECKPOINT_DB=/app/data/checkpoints.db
EXPOSE 7860
CMD ["/app/deploy/start.sh"]
