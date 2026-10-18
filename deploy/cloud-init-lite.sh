#!/bin/bash
# The light demo box (DEPLOYMENT_PLAN §6): Docker plus the single-container image from deploy/container, behind Caddy
# on the host with a Let's Encrypt certificate for epicenter.<ip>.sslip.io (the bare IP redirects there).
# Used by `INSTANCE_TYPE=m7i-flex.large USER_DATA=deploy/cloud-init-lite.sh deploy/aws.sh create`. No example
# environments, no compose stack: the hosted demo runs the committed samples and RCAEval replays only.
set -euxo pipefail
apt-get update
apt-get install -y docker.io git caddy
systemctl enable --now docker
git clone --depth 1 https://github.com/Prateek1771/epicenter /opt/epicenter
docker build -t epicenter-demo /opt/epicenter/deploy/container

# the public IP (IMDSv2) names the site: an Elastic IP associated after boot shows up here once it's attached
TOKEN=$(curl -sX PUT http://169.254.169.254/latest/api/token -H "X-aws-ec2-metadata-token-ttl-seconds: 300")
for _ in $(seq 1 60); do
  IP=$(curl -s -H "X-aws-ec2-metadata-token: $TOKEN" http://169.254.169.254/latest/meta-data/public-ipv4 || true)
  [ -n "$IP" ] && break; sleep 5
done
HOST="epicenter.${IP//./-}.sslip.io"

docker run -d --name epicenter --restart unless-stopped -p 127.0.0.1:7860:7860 -e PUBLIC_URL="https://$HOST" \
  epicenter-demo
cat > /etc/caddy/Caddyfile <<EOF
$HOST {
	encode {
		gzip
		match {
			header Content-Type text/html*
			header Content-Type text/css*
			header Content-Type application/json*
			header Content-Type application/javascript*
		}
	}
	reverse_proxy 127.0.0.1:7860 {
		flush_interval -1
	}
}
http://$IP {
	redir https://$HOST{uri} permanent
}
EOF
systemctl restart caddy
echo "https://$HOST" > /opt/READY
