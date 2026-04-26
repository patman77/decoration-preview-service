#!/usr/bin/env bash
set -euo pipefail

REGION="eu-central-1"
CLUSTER="decoration-preview-cluster"
SPECIFIC_EIP_IP="52.58.157.195"

require_tools() {
  if ! command -v aws >/dev/null 2>&1; then
    echo "Error: aws CLI not found in PATH." >&2
    exit 1
  fi

  if ! command -v jq >/dev/null 2>&1; then
    echo "Error: jq not found in PATH." >&2
    exit 1
  fi
}

delete_nat_gateways() {
  echo "Deleting NAT gateways (major hourly cost source)..."
  NAT_GWS=$(aws ec2 describe-nat-gateways \
    --region "$REGION" \
    --filter Name=state,Values=available,pending,failed \
    --query 'NatGateways[].NatGatewayId' \
    --output text 2>/dev/null || true)

  if [ -n "${NAT_GWS:-}" ]; then
    for NAT_GW in $NAT_GWS; do
      echo "Deleting NAT gateway $NAT_GW"
      aws ec2 delete-nat-gateway \
        --region "$REGION" \
        --nat-gateway-id "$NAT_GW" >/dev/null || true
    done
  else
    echo "No NAT gateways found."
  fi
}

release_specific_elastic_ip() {
  echo "Checking for specific Elastic IP ${SPECIFIC_EIP_IP}..."

  local eip_json
  eip_json=$(aws ec2 describe-addresses \
    --region "$REGION" \
    --public-ips "$SPECIFIC_EIP_IP" \
    --output json 2>/dev/null || true)

  if [[ -z "${eip_json:-}" || "$(echo "$eip_json" | jq '.Addresses | length')" -eq 0 ]]; then
    echo "Specific Elastic IP ${SPECIFIC_EIP_IP} not found in region ${REGION}."
    return
  fi

  local allocation_id association_id
  allocation_id=$(echo "$eip_json" | jq -r '.Addresses[0].AllocationId // empty')
  association_id=$(echo "$eip_json" | jq -r '.Addresses[0].AssociationId // empty')

  if [[ -z "$allocation_id" ]]; then
    echo "Could not resolve allocation id for ${SPECIFIC_EIP_IP}; skipping."
    return
  fi

  if [[ -n "$association_id" ]]; then
    echo "Elastic IP ${SPECIFIC_EIP_IP} is still attached (association ${association_id}); skipping forced release."
    return
  fi

  echo "Releasing specific unattached Elastic IP ${SPECIFIC_EIP_IP} (${allocation_id})"
  aws ec2 release-address \
    --region "$REGION" \
    --allocation-id "$allocation_id" >/dev/null || true
}

release_unattached_elastic_ips() {
  echo "Releasing unattached Elastic IPs..."
  EIP_ALLOCS=$(aws ec2 describe-addresses \
    --region "$REGION" \
    --query 'Addresses[?AssociationId==null].AllocationId' \
    --output text 2>/dev/null || true)

  if [ -n "${EIP_ALLOCS:-}" ]; then
    for EIP_ALLOC in $EIP_ALLOCS; do
      echo "Releasing EIP allocation $EIP_ALLOC"
      aws ec2 release-address \
        --region "$REGION" \
        --allocation-id "$EIP_ALLOC" >/dev/null || true
    done
  else
    echo "No unattached Elastic IPs found."
  fi
}

delete_waf_web_acls() {
  echo "Deleting WAFv2 Web ACLs and their associations/rules..."

  local scopes=("REGIONAL" "CLOUDFRONT")
  local resource_types=(
    "APPLICATION_LOAD_BALANCER"
    "API_GATEWAY"
    "APPSYNC"
    "COGNITO_USER_POOL"
    "APP_RUNNER_SERVICE"
    "VERIFIED_ACCESS_INSTANCE"
    "AMPLIFY"
  )

  for scope in "${scopes[@]}"; do
    local waf_region="$REGION"
    if [[ "$scope" == "CLOUDFRONT" ]]; then
      waf_region="us-east-1"
    fi

    echo "Processing WAF scope=${scope} region=${waf_region}"

    local web_acls_json
    web_acls_json=$(aws wafv2 list-web-acls \
      --scope "$scope" \
      --region "$waf_region" \
      --output json 2>/dev/null || true)

    local acl_count
    acl_count=$(echo "${web_acls_json:-{\"WebACLs\":[]}}" | jq '.WebACLs | length')

    if [[ "$acl_count" -eq 0 ]]; then
      echo "No WAF Web ACLs found for scope ${scope}."
      continue
    fi

    while IFS= read -r acl; do
      [[ -z "$acl" ]] && continue

      local acl_name acl_id acl_arn
      acl_name=$(echo "$acl" | jq -r '.Name')
      acl_id=$(echo "$acl" | jq -r '.Id')
      acl_arn=$(echo "$acl" | jq -r '.ARN')

      echo "Found Web ACL ${acl_name} (${acl_arn})"

      for rt in "${resource_types[@]}"; do
        local resources
        resources=$(aws wafv2 list-resources-for-web-acl \
          --web-acl-arn "$acl_arn" \
          --resource-type "$rt" \
          --region "$waf_region" \
          --query 'ResourceArns[]' \
          --output text 2>/dev/null || true)

        if [[ -n "${resources:-}" ]]; then
          for resource_arn in $resources; do
            echo "Disassociating Web ACL ${acl_name} from ${resource_arn}"
            aws wafv2 disassociate-web-acl \
              --resource-arn "$resource_arn" \
              --region "$waf_region" >/dev/null || true
          done
        fi
      done

      local lock_token
      lock_token=$(aws wafv2 get-web-acl \
        --name "$acl_name" \
        --id "$acl_id" \
        --scope "$scope" \
        --region "$waf_region" \
        --query 'LockToken' \
        --output text 2>/dev/null || true)

      if [[ -z "${lock_token:-}" || "$lock_token" == "None" ]]; then
        echo "Unable to get lock token for Web ACL ${acl_name}; skipping delete."
        continue
      fi

      echo "Deleting Web ACL ${acl_name}"
      aws wafv2 delete-web-acl \
        --name "$acl_name" \
        --id "$acl_id" \
        --scope "$scope" \
        --lock-token "$lock_token" \
        --region "$waf_region" >/dev/null || true
    done < <(echo "$web_acls_json" | jq -c '.WebACLs[]?')
  done
}

delete_unused_kms_keys() {
  echo "Scheduling deletion for customer-managed KMS keys..."

  local key_ids
  key_ids=$(aws kms list-keys \
    --region "$REGION" \
    --query 'Keys[].KeyId' \
    --output text 2>/dev/null || true)

  if [[ -z "${key_ids:-}" ]]; then
    echo "No KMS keys returned."
    return
  fi

  for key_id in $key_ids; do
    local key_metadata_json
    key_metadata_json=$(aws kms describe-key \
      --region "$REGION" \
      --key-id "$key_id" \
      --output json 2>/dev/null || true)

    [[ -z "${key_metadata_json:-}" ]] && continue

    local manager state arn
    manager=$(echo "$key_metadata_json" | jq -r '.KeyMetadata.KeyManager // empty')
    state=$(echo "$key_metadata_json" | jq -r '.KeyMetadata.KeyState // empty')
    arn=$(echo "$key_metadata_json" | jq -r '.KeyMetadata.Arn // empty')

    if [[ "$manager" != "CUSTOMER" ]]; then
      echo "Skipping AWS-managed key ${key_id}"
      continue
    fi

    if [[ "$state" == "PendingDeletion" ]]; then
      echo "Key already pending deletion: ${arn:-$key_id}"
      continue
    fi

    echo "Disabling key ${arn:-$key_id} (state=${state})"
    aws kms disable-key \
      --region "$REGION" \
      --key-id "$key_id" >/dev/null 2>&1 || true

    echo "Scheduling deletion for ${arn:-$key_id} (7 days)"
    aws kms schedule-key-deletion \
      --region "$REGION" \
      --key-id "$key_id" \
      --pending-window-in-days 7 >/dev/null || true
  done
}

delete_amis_and_snapshots() {
  echo "Deregistering self-owned AMIs and deleting snapshots..."

  local images_json
  images_json=$(aws ec2 describe-images \
    --region "$REGION" \
    --owners self \
    --output json 2>/dev/null || true)

  local image_count
  image_count=$(echo "${images_json:-{\"Images\":[]}}" | jq '.Images | length')

  if [[ "$image_count" -gt 0 ]]; then
    while IFS= read -r image_id; do
      [[ -z "$image_id" ]] && continue
      echo "Deregistering AMI ${image_id}"
      aws ec2 deregister-image \
        --region "$REGION" \
        --image-id "$image_id" >/dev/null || true
    done < <(echo "$images_json" | jq -r '.Images[]?.ImageId')

    while IFS= read -r snap_id; do
      [[ -z "$snap_id" ]] && continue
      echo "Deleting AMI-linked snapshot ${snap_id}"
      aws ec2 delete-snapshot \
        --region "$REGION" \
        --snapshot-id "$snap_id" >/dev/null || true
    done < <(echo "$images_json" | jq -r '.Images[]?.BlockDeviceMappings[]?.Ebs?.SnapshotId // empty' | sort -u)
  else
    echo "No self-owned AMIs found."
  fi

  local snapshots
  snapshots=$(aws ec2 describe-snapshots \
    --region "$REGION" \
    --owner-ids self \
    --query 'Snapshots[].SnapshotId' \
    --output text 2>/dev/null || true)

  if [[ -n "${snapshots:-}" ]]; then
    for snapshot_id in $snapshots; do
      echo "Deleting snapshot ${snapshot_id}"
      aws ec2 delete-snapshot \
        --region "$REGION" \
        --snapshot-id "$snapshot_id" >/dev/null || true
    done
  else
    echo "No remaining self-owned snapshots found."
  fi
}

require_tools

echo "=== AWS cleanup started for region: $REGION ==="

echo
echo "1) List ECS services"
SERVICES=$(aws ecs list-services \
  --region "$REGION" \
  --cluster "$CLUSTER" \
  --query 'serviceArns[]' \
  --output text || true)

if [ -n "${SERVICES:-}" ]; then
  echo "Found ECS services:"
  echo "$SERVICES"

  echo
  echo "2) Scale ECS services down to 0"
  for SERVICE_ARN in $SERVICES; do
    SERVICE_NAME=$(basename "$SERVICE_ARN")
    echo "Scaling down $SERVICE_NAME"
    aws ecs update-service \
      --region "$REGION" \
      --cluster "$CLUSTER" \
      --service "$SERVICE_NAME" \
      --desired-count 0 >/dev/null
  done

  echo
  echo "Waiting briefly for tasks to stop..."
  sleep 20

  echo
  echo "3) Force-stop remaining ECS tasks if any"
  TASKS=$(aws ecs list-tasks \
    --region "$REGION" \
    --cluster "$CLUSTER" \
    --query 'taskArns[]' \
    --output text || true)

  if [ -n "${TASKS:-}" ]; then
    for TASK_ARN in $TASKS; do
      echo "Stopping task $TASK_ARN"
      aws ecs stop-task \
        --region "$REGION" \
        --cluster "$CLUSTER" \
        --task "$TASK_ARN" >/dev/null || true
    done
  else
    echo "No running ECS tasks found."
  fi

  echo
  echo "Waiting again..."
  sleep 15

  echo
  echo "4) Delete ECS services"
  for SERVICE_ARN in $SERVICES; do
    SERVICE_NAME=$(basename "$SERVICE_ARN")
    echo "Deleting service $SERVICE_NAME"
    aws ecs delete-service \
      --region "$REGION" \
      --cluster "$CLUSTER" \
      --service "$SERVICE_NAME" \
      --force >/dev/null || true
  done
else
  echo "No ECS services found in cluster $CLUSTER"
fi

echo
echo "5) Delete NAT gateways"
delete_nat_gateways

echo
echo "6) Delete load balancers"
LB_ARNS=$(aws elbv2 describe-load-balancers \
  --region "$REGION" \
  --query 'LoadBalancers[].LoadBalancerArn' \
  --output text || true)

if [ -n "${LB_ARNS:-}" ]; then
  for LB_ARN in $LB_ARNS; do
    echo "Deleting load balancer $LB_ARN"
    aws elbv2 delete-load-balancer \
      --region "$REGION" \
      --load-balancer-arn "$LB_ARN" || true
  done
else
  echo "No load balancers found."
fi

echo
echo "Waiting for ALB deletion propagation..."
sleep 20

echo
echo "7) Delete target groups"
TG_ARNS=$(aws elbv2 describe-target-groups \
  --region "$REGION" \
  --query 'TargetGroups[].TargetGroupArn' \
  --output text || true)

if [ -n "${TG_ARNS:-}" ]; then
  for TG_ARN in $TG_ARNS; do
    echo "Deleting target group $TG_ARN"
    aws elbv2 delete-target-group \
      --region "$REGION" \
      --target-group-arn "$TG_ARN" || true
  done
else
  echo "No target groups found."
fi

echo
echo "8) Delete ECR repositories and images"
REPOS=$(aws ecr describe-repositories \
  --region "$REGION" \
  --query 'repositories[].repositoryName' \
  --output text || true)

if [ -n "${REPOS:-}" ]; then
  for REPO in $REPOS; do
    echo "Deleting ECR repo $REPO"
    aws ecr delete-repository \
      --region "$REGION" \
      --repository-name "$REPO" \
      --force || true
  done
else
  echo "No ECR repositories found."
fi

echo
echo "9) Delete CloudWatch log groups"
LOG_GROUPS=$(aws logs describe-log-groups \
  --region "$REGION" \
  --query 'logGroups[].logGroupName' \
  --output text || true)

if [ -n "${LOG_GROUPS:-}" ]; then
  for LG in $LOG_GROUPS; do
    echo "Deleting log group $LG"
    aws logs delete-log-group \
      --region "$REGION" \
      --log-group-name "$LG" || true
  done
else
  echo "No CloudWatch log groups found."
fi

echo
echo "10) Delete WAF Web ACLs and associated rules"
delete_waf_web_acls

echo
echo "11) Release specific Elastic IP ($SPECIFIC_EIP_IP) if unattached"
release_specific_elastic_ip

echo
echo "12) Release unattached Elastic IPs"
release_unattached_elastic_ips

echo
echo "13) Delete unused customer-managed KMS keys"
delete_unused_kms_keys

echo
echo "14) Deregister AMIs and delete EBS snapshots"
delete_amis_and_snapshots

echo
echo "15) Optional: list remaining cost-relevant resources"
echo "--- ECS clusters ---"
aws ecs list-clusters --region "$REGION" || true

echo "--- Load balancers ---"
aws elbv2 describe-load-balancers --region "$REGION" || true

echo "--- ECR repos ---"
aws ecr describe-repositories --region "$REGION" || true

echo "--- Log groups ---"
aws logs describe-log-groups --region "$REGION" || true

echo "--- NAT gateways ---"
aws ec2 describe-nat-gateways --region "$REGION" --output text || true

echo "--- Elastic IPs ---"
aws ec2 describe-addresses --region "$REGION" --output text || true

echo "--- WAF Web ACLs (REGIONAL) ---"
aws wafv2 list-web-acls --scope REGIONAL --region "$REGION" || true

echo "--- WAF Web ACLs (CLOUDFRONT / us-east-1) ---"
aws wafv2 list-web-acls --scope CLOUDFRONT --region us-east-1 || true

echo "--- Customer-managed KMS keys ---"
aws kms list-keys --region "$REGION" --output text || true

echo "--- Self-owned AMIs ---"
aws ec2 describe-images --region "$REGION" --owners self --query 'Images[].ImageId' --output text || true

echo "--- Self-owned snapshots ---"
aws ec2 describe-snapshots --region "$REGION" --owner-ids self --query 'Snapshots[].SnapshotId' --output text || true

echo
echo "=== Cleanup finished ==="
