#!/bin/bash
# EC2 user-data for the demo box (phase 11, ADR 0013). Ubuntu 24.04. NO SECRETS here: user-data is readable from the
# console and the metadata service. Epicenter itself is uploaded by `aws.sh create` (the working tree, no .env); this
# only installs tools and clones the two example systems. Writes /opt/READY when done.
set -euxo pipefail
exec > /var/log/epicenter-init.log 2>&1
export DEBIAN_FRONTEND=noninteractive

apt-get update
apt-get install -y ca-certificates curl gnupg git jq python3.12 python3.12-venv python3-pip unzip

# Docker Engine + compose plugin (Docker's apt repo)
install -m 0755 -d /etc/apt/keyrings
curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" > /etc/apt/sources.list.d/docker.list
# Node 22 (NodeSource) and k6 (Grafana)
curl -fsSL https://deb.nodesource.com/setup_22.x | bash -
curl -fsSL https://dl.k6.io/key.gpg | gpg --dearmor -o /etc/apt/keyrings/k6.gpg
echo "deb [signed-by=/etc/apt/keyrings/k6.gpg] https://dl.k6.io/deb stable main" > /etc/apt/sources.list.d/k6.list
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin nodejs k6
usermod -aG docker ubuntu
curl -LsSf https://astral.sh/uv/install.sh | env UV_INSTALL_DIR=/usr/local/bin sh
corepack enable

# flip-node runs on the host and reaches Mongo by this name; containers get it from extra_hosts: host-gateway
grep -q host.docker.internal /etc/hosts || echo "127.0.0.1 host.docker.internal" >> /etc/hosts
# OpenSearch (OTel Demo) needs this
echo "vm.max_map_count=262144" > /etc/sysctl.d/99-epicenter.conf
sysctl --system
# swap: survives a memory spike during image builds
if [ ! -f /swapfile ]; then
  fallocate -l 4G /swapfile && chmod 600 /swapfile && mkswap /swapfile && swapon /swapfile
  echo "/swapfile none swap sw 0 0" >> /etc/fstab
fi

# the example systems (public). flip-node is built in this throwaway clone: dist/ is git-ignored there and the source
# is never edited (AGENTS hard rule 10)
cd /opt
[ -d opentelemetry-demo ] || git clone --depth 1 --branch 3.1.0 https://github.com/open-telemetry/opentelemetry-demo
[ -d system-design-journey ] || git clone --depth 1 https://github.com/xDAnkit/system-design-journey
mkdir -p /opt/epicenter
chown -R ubuntu:ubuntu /opt/opentelemetry-demo /opt/system-design-journey /opt/epicenter
cd /opt/system-design-journey/season-1/2.vertical-vs-horizontal-scaling/servers/01-node
sudo -u ubuntu -H bash -c 'corepack pnpm install --frozen-lockfile && corepack pnpm run build'

touch /opt/READY
