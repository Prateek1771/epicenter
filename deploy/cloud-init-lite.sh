#!/bin/bash
# The light demo box (DEPLOYMENT_PLAN §6): Docker plus the single-container image from deploy/container, on port 80.
# Used by `INSTANCE_TYPE=t3.large USER_DATA=deploy/cloud-init-lite.sh deploy/aws.sh create`. No example environments,
# no compose stack: the hosted demo runs the committed samples and RCAEval replays only.
set -euxo pipefail
apt-get update
apt-get install -y docker.io git
systemctl enable --now docker
git clone --depth 1 https://github.com/Prateek1771/epicenter /opt/epicenter
docker build -t epicenter-demo /opt/epicenter/deploy/container
docker run -d --name epicenter --restart unless-stopped -p 80:7860 epicenter-demo
touch /opt/READY
