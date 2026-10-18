#!/usr/bin/env bash
# Demo box on AWS (phase 11, ADR 0013): create → rehearse → stop → start on demo day → destroy. AWS CLI v2.
#   AWS_PROFILE=epicenter-demo AWS_REGION=ap-south-1 deploy/aws.sh create|start|stop|status|ssh|upload|allow-my-ip|destroy
# Every resource is tagged Project=epicenter-demo; `destroy` finds them by tag.
set -euo pipefail

NAME=epicenter-demo
TAG="Key=Project,Value=$NAME"
TYPE=${INSTANCE_TYPE:-m6i.2xlarge}
DISK_GB=${DISK_GB:-60}
KEY="$HOME/.ssh/$NAME.pem"
ROOT=$(cd "$(dirname "$0")/.." && pwd)
: "${AWS_REGION:?set AWS_REGION (and AWS_PROFILE) first}"
export AWS_PAGER=""

ec2() { aws ec2 "$@" --output text; }
instance_id() {
  ec2 describe-instances --filters "Name=tag:Project,Values=$NAME" \
    "Name=instance-state-name,Values=pending,running,stopping,stopped" --query 'Reservations[].Instances[].InstanceId'
}
eip() { ec2 describe-addresses --filters "Name=tag:Project,Values=$NAME" --query 'Addresses[0].[AllocationId,PublicIp]'; }
sg_id() { ec2 describe-security-groups --filters "Name=group-name,Values=$NAME" --query 'SecurityGroups[0].GroupId'; }
host_of() { echo "${1//./-}.sslip.io"; }
ip() { eip | cut -f2; }
ssh_box() { ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -o ConnectTimeout=10 "ubuntu@$(ip)" "$@"; }
my_ip() { curl -fsS https://checkip.amazonaws.com | tr -d '[:space:]'; }

upload() {
  # the working tree as you tested it: no secrets, no data, no build output
  tar -C "$ROOT" -czf - --exclude=.git --exclude='.env' --exclude='.env.openconnector' --exclude=data \
    --exclude=node_modules --exclude=.next --exclude='__pycache__' --exclude='examples/run' \
    --exclude='examples/*/run' . | ssh_box 'tar -C /opt/epicenter -xzf - && chmod +x /opt/epicenter/deploy/*.sh'
  echo "uploaded to /opt/epicenter"
}

case "${1:-}" in
create)
  [ -z "$(instance_id)" ] || { echo "already exists: $(instance_id)"; exit 1; }
  if [ ! -f "$KEY" ]; then
    ec2 create-key-pair --key-name "$NAME" --key-type ed25519 --tag-specifications "ResourceType=key-pair,Tags=[{$TAG}]" \
      --query KeyMaterial > "$KEY"
    chmod 600 "$KEY"
  fi
  vpc=$(ec2 describe-vpcs --filters Name=isDefault,Values=true --query 'Vpcs[0].VpcId')
  sg=$(sg_id)
  if [ "$sg" = "None" ] || [ -z "$sg" ]; then
    sg=$(ec2 create-security-group --group-name "$NAME" --description "Epicenter demo: 80/443 public, 22 from presenter" \
      --vpc-id "$vpc" --tag-specifications "ResourceType=security-group,Tags=[{$TAG}]" --query GroupId)
    for p in 80 443; do ec2 authorize-security-group-ingress --group-id "$sg" --protocol tcp --port $p --cidr 0.0.0.0/0 >/dev/null; done
    ec2 authorize-security-group-ingress --group-id "$sg" --protocol tcp --port 22 --cidr "$(my_ip)/32" >/dev/null
  fi
  read -r alloc addr <<< "$(eip)"
  if [ "$alloc" = "None" ] || [ -z "$alloc" ]; then
    read -r alloc addr <<< "$(ec2 allocate-address --domain vpc --tag-specifications "ResourceType=elastic-ip,Tags=[{$TAG}]" \
      --query '[AllocationId,PublicIp]')"
  fi
  ami=$(aws ssm get-parameters --names /aws/service/canonical/ubuntu/server/24.04/stable/current/amd64/hvm/ebs-gp3/ami-id \
    --query 'Parameters[0].Value' --output text)
  id=$(ec2 run-instances --image-id "$ami" --instance-type "$TYPE" --key-name "$NAME" --security-group-ids "$sg" \
    --user-data "file://$ROOT/deploy/cloud-init.sh" \
    --metadata-options HttpTokens=required,HttpEndpoint=enabled \
    --block-device-mappings "DeviceName=/dev/sda1,Ebs={VolumeSize=$DISK_GB,VolumeType=gp3,DeleteOnTermination=true}" \
    --tag-specifications "ResourceType=instance,Tags=[{$TAG},{Key=Name,Value=$NAME}]" "ResourceType=volume,Tags=[{$TAG}]" \
    --query 'Instances[0].InstanceId')
  echo "instance $id ($TYPE) starting…"
  aws ec2 wait instance-running --instance-ids "$id"
  ec2 associate-address --instance-id "$id" --allocation-id "$alloc" >/dev/null
  echo "waiting for cloud-init (~10 min: Docker, Node, clones, flip-node build)…"
  for _ in $(seq 1 90); do ssh_box test -f /opt/READY 2>/dev/null && break; sleep 20; done
  ssh_box test -f /opt/READY || { echo "not ready: check ssh … sudo tail /var/log/epicenter-init.log"; exit 1; }
  upload
  echo "ready: https://$(host_of "$addr")  next: deploy/aws.sh ssh, then /opt/epicenter/deploy/demo.sh up"
  ;;
start)
  aws ec2 start-instances --instance-ids "$(instance_id)" >/dev/null
  aws ec2 wait instance-running --instance-ids "$(instance_id)"
  echo "running: https://$(host_of "$(ip)")"
  ;;
stop)
  aws ec2 stop-instances --instance-ids "$(instance_id)" >/dev/null
  echo "stopping (EBS + idle Elastic IP still cost ~\$0.30/day; destroy when done)"
  ;;
status)
  id=$(instance_id)
  [ -n "$id" ] || { echo "no instance"; exit 0; }
  ec2 describe-instances --instance-ids "$id" --query 'Reservations[0].Instances[0].[InstanceId,InstanceType,State.Name,LaunchTime]'
  echo "https://$(host_of "$(ip)")"
  ;;
ssh)
  shift
  # tunnels: FalkorDB browser and the raw API, which Caddy doesn't expose
  ssh -i "$KEY" -o StrictHostKeyChecking=accept-new -L 3002:127.0.0.1:3002 -L 8000:127.0.0.1:8000 "ubuntu@$(ip)" "$@"
  ;;
upload) upload ;;
allow-my-ip)
  ec2 authorize-security-group-ingress --group-id "$(sg_id)" --protocol tcp --port 22 --cidr "$(my_ip)/32" >/dev/null \
    && echo "22 open for $(my_ip)" || echo "already open for $(my_ip)"
  ;;
destroy)
  echo "Resources tagged Project=$NAME:"
  aws resourcegroupstaggingapi get-resources --tag-filters "Key=Project,Values=$NAME" --query 'ResourceTagMappingList[].ResourceARN' --output text | tr '\t' '\n'
  read -r -p "Delete all of them? [y/N] " ok
  [ "$ok" = "y" ] || { echo "kept"; exit 0; }
  id=$(instance_id)
  if [ -n "$id" ]; then aws ec2 terminate-instances --instance-ids "$id" >/dev/null; aws ec2 wait instance-terminated --instance-ids "$id"; fi
  read -r alloc _ <<< "$(eip)"
  [ "$alloc" = "None" ] || [ -z "$alloc" ] || ec2 release-address --allocation-id "$alloc"
  sg=$(sg_id); [ "$sg" = "None" ] || [ -z "$sg" ] || ec2 delete-security-group --group-id "$sg"
  ec2 delete-key-pair --key-name "$NAME" >/dev/null 2>&1 || true
  rm -f "$KEY"
  left=$(ec2 describe-volumes --filters "Name=tag:Project,Values=$NAME" --query 'Volumes[].VolumeId')
  snaps=$(ec2 describe-snapshots --owner-ids self --filters "Name=tag:Project,Values=$NAME" --query 'Snapshots[].SnapshotId')
  [ -z "$left$snaps" ] && echo "destroyed: nothing tagged $NAME is left" || echo "LEFT OVER: $left $snaps"
  ;;
*)
  sed -n '2,5p' "$0"; exit 2 ;;
esac
