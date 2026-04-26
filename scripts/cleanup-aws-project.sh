#!/usr/bin/env bash
set -euo pipefail

print_help() {
  cat <<'EOF'
Usage:
  cleanup-aws-project.sh [options]

Description:
  Cleans up AWS resources for a project by matching names/tags and ECS cluster resources.

Defaults:
  --region              eu-central-1
  --cluster             decoration-preview-cluster
  --name-filter         decoration-preview
  --specific-eip        52.58.157.195
  --wait-ecs            20
  --wait-lb             20
  --wait-post-stop      15

Options:
  --region REGION
      AWS region to use.

  --cluster CLUSTER
      ECS cluster name.

  --name-filter FILTER
      Substring used to match resources for deletion.
      Examples: decoration-preview, my-stack, demo-app

  --specific-eip PUBLIC_IP
      Extra Elastic IP to release if unattached, even if it does not match --name-filter.

  --profile PROFILE
      AWS CLI profile to use.

  --wait-ecs SECONDS
      Seconds to wait after scaling ECS services down.

  --wait-post-stop SECONDS
      Seconds to wait after stopping ECS tasks.

  --wait-lb SECONDS
      Seconds to wait after deleting load balancers before deleting target groups.

  --dry-run
      Show what would be deleted, but do not delete anything.

  --delete-log-groups
      Also delete matching CloudWatch log groups.

  --delete-ecr
      Also delete matching ECR repositories.

  --delete-load-balancers
      Also delete matching load balancers and target groups.

  --delete-network
      Also delete matching NAT gateways and release matching/unattached Elastic IPs.

  --delete-ecs
      Also scale down and delete matching ECS services and their tasks.

  --delete-waf
      Also delete matching WAFv2 Web ACLs (including associated rules and associations).

  --delete-kms
      Also schedule deletion for matching customer-managed KMS keys.

  --delete-storage
      Also deregister matching AMIs and delete matching EBS snapshots.

  --delete-all
      Enable all delete categories above.

  --force
      Skip confirmation prompt.

  --help, -h
      Show this help text.

Examples:
  Dry run:
    ./cleanup-aws-project.sh --cluster decoration-preview-cluster --name-filter decoration-preview --delete-all --dry-run

  Delete everything matching filter:
    ./cleanup-aws-project.sh --cluster decoration-preview-cluster --name-filter decoration-preview --delete-all

  Use a specific profile and region:
    ./cleanup-aws-project.sh --profile personal --region eu-west-1 --cluster my-cluster --name-filter my-app --delete-all --force

Notes:
  - Requires: aws, jq
  - Make sure your AWS credentials are configured.
  - Matching is substring-based, so choose --name-filter carefully.
  - KMS deletion is scheduled (minimum 7-day waiting period by AWS).
EOF
}

REGION="eu-central-1"
CLUSTER="decoration-preview-cluster"
NAME_FILTER="decoration-preview"
SPECIFIC_EIP_IP="52.58.157.195"
PROFILE=""
WAIT_ECS=20
WAIT_POST_STOP=15
WAIT_LB=20

DRY_RUN=0
DELETE_LOG_GROUPS=0
DELETE_ECR=0
DELETE_LOAD_BALANCERS=0
DELETE_NETWORK=0
DELETE_ECS=0
DELETE_WAF=0
DELETE_KMS=0
DELETE_STORAGE=0
FORCE=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --region)
      REGION="${2:?Missing value for --region}"
      shift 2
      ;;
    --cluster)
      CLUSTER="${2:?Missing value for --cluster}"
      shift 2
      ;;
    --name-filter)
      NAME_FILTER="${2:?Missing value for --name-filter}"
      shift 2
      ;;
    --specific-eip)
      SPECIFIC_EIP_IP="${2:?Missing value for --specific-eip}"
      shift 2
      ;;
    --profile)
      PROFILE="${2:?Missing value for --profile}"
      shift 2
      ;;
    --wait-ecs)
      WAIT_ECS="${2:?Missing value for --wait-ecs}"
      shift 2
      ;;
    --wait-post-stop)
      WAIT_POST_STOP="${2:?Missing value for --wait-post-stop}"
      shift 2
      ;;
    --wait-lb)
      WAIT_LB="${2:?Missing value for --wait-lb}"
      shift 2
      ;;
    --dry-run)
      DRY_RUN=1
      shift
      ;;
    --delete-log-groups)
      DELETE_LOG_GROUPS=1
      shift
      ;;
    --delete-ecr)
      DELETE_ECR=1
      shift
      ;;
    --delete-load-balancers)
      DELETE_LOAD_BALANCERS=1
      shift
      ;;
    --delete-network)
      DELETE_NETWORK=1
      shift
      ;;
    --delete-ecs)
      DELETE_ECS=1
      shift
      ;;
    --delete-waf)
      DELETE_WAF=1
      shift
      ;;
    --delete-kms)
      DELETE_KMS=1
      shift
      ;;
    --delete-storage)
      DELETE_STORAGE=1
      shift
      ;;
    --delete-all)
      DELETE_LOG_GROUPS=1
      DELETE_ECR=1
      DELETE_LOAD_BALANCERS=1
      DELETE_NETWORK=1
      DELETE_ECS=1
      DELETE_WAF=1
      DELETE_KMS=1
      DELETE_STORAGE=1
      shift
      ;;
    --force)
      FORCE=1
      shift
      ;;
    --help|-h)
      print_help
      exit 0
      ;;
    *)
      echo "Unknown argument: $1" >&2
      echo "Use --help to see available options." >&2
      exit 1
      ;;
  esac
done

if ! command -v aws >/dev/null 2>&1; then
  echo "Error: aws CLI not found in PATH." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Error: jq not found in PATH." >&2
  exit 1
fi

AWS_ARGS=(--region "$REGION")
if [[ -n "$PROFILE" ]]; then
  AWS_ARGS+=(--profile "$PROFILE")
fi

contains_filter() {
  local value="${1:-}"
  [[ "$value" == *"$NAME_FILTER"* ]]
}

run_cmd() {
  if [[ "$DRY_RUN" -eq 1 ]]; then
    echo "[dry-run] $*"
  else
    eval "$@"
  fi
}

echo "=== Targeted AWS cleanup started ==="
echo "Region:                 $REGION"
echo "Cluster:                $CLUSTER"
echo "Name filter:            $NAME_FILTER"
echo "Specific EIP:           $SPECIFIC_EIP_IP"
echo "Profile:                ${PROFILE:-<default>}"
echo "Delete ECS:             $DELETE_ECS"
echo "Delete load balancers:  $DELETE_LOAD_BALANCERS"
echo "Delete network:         $DELETE_NETWORK"
echo "Delete WAF:             $DELETE_WAF"
echo "Delete KMS:             $DELETE_KMS"
echo "Delete storage:         $DELETE_STORAGE"
echo "Delete ECR:             $DELETE_ECR"
echo "Delete log groups:      $DELETE_LOG_GROUPS"
echo "Dry run:                $DRY_RUN"
echo

if [[ "$DELETE_ECS" -eq 0 && "$DELETE_LOAD_BALANCERS" -eq 0 && "$DELETE_NETWORK" -eq 0 && "$DELETE_WAF" -eq 0 && "$DELETE_KMS" -eq 0 && "$DELETE_STORAGE" -eq 0 && "$DELETE_ECR" -eq 0 && "$DELETE_LOG_GROUPS" -eq 0 ]]; then
  echo "Nothing selected for deletion."
  echo "Use one of: --delete-ecs, --delete-load-balancers, --delete-network, --delete-waf, --delete-kms, --delete-storage, --delete-ecr, --delete-log-groups, or --delete-all"
  exit 1
fi

if [[ "$FORCE" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
  read -r -p "Proceed with deletion of resources matching '$NAME_FILTER' in region '$REGION'? [y/N] " REPLY
  case "$REPLY" in
    y|Y|yes|YES) ;;
    *)
      echo "Aborted."
      exit 0
      ;;
  esac
fi

delete_ecs() {
  echo "1) ECS cleanup"

  SERVICE_ARNS=$(aws "${AWS_ARGS[@]}" ecs list-services \
    --cluster "$CLUSTER" \
    --query 'serviceArns[]' \
    --output text 2>/dev/null || true)

  local matched_services=()
  if [[ -n "${SERVICE_ARNS:-}" ]]; then
    for arn in $SERVICE_ARNS; do
      local name
      name=$(basename "$arn")
      if contains_filter "$name"; then
        matched_services+=("$name")
      fi
    done
  fi

  if [[ ${#matched_services[@]} -eq 0 ]]; then
    echo "No matching ECS services found."
    echo
    return
  fi

  echo "Matched ECS services:"
  printf '  - %s\n' "${matched_services[@]}"

  echo "Scaling matched services to 0..."
  for service in "${matched_services[@]}"; do
    run_cmd "aws ${AWS_ARGS[*]} ecs update-service --cluster \"$CLUSTER\" --service \"$service\" --desired-count 0 >/dev/null"
  done

  if [[ "$DRY_RUN" -eq 0 ]]; then
    echo "Waiting ${WAIT_ECS}s for ECS to drain..."
    sleep "$WAIT_ECS"
  fi

  TASK_ARNS=$(aws "${AWS_ARGS[@]}" ecs list-tasks \
    --cluster "$CLUSTER" \
    --query 'taskArns[]' \
    --output text 2>/dev/null || true)

  if [[ -n "${TASK_ARNS:-}" ]]; then
    TASK_DETAILS=$(aws "${AWS_ARGS[@]}" ecs describe-tasks \
      --cluster "$CLUSTER" \
      --tasks $TASK_ARNS \
      --output json)

    for service in "${matched_services[@]}"; do
      MATCHING_TASKS=$(echo "$TASK_DETAILS" | jq -r --arg svc "$service" '
        .tasks[]?
        | select((.group // "") == ("service:" + $svc))
        | .taskArn
      ')

      if [[ -n "${MATCHING_TASKS:-}" ]]; then
        while IFS= read -r task_arn; do
          [[ -z "$task_arn" ]] && continue
          run_cmd "aws ${AWS_ARGS[*]} ecs stop-task --cluster \"$CLUSTER\" --task \"$task_arn\" >/dev/null || true"
        done <<< "$MATCHING_TASKS"
      fi
    done
  fi

  if [[ "$DRY_RUN" -eq 0 ]]; then
    echo "Waiting ${WAIT_POST_STOP}s after task stop..."
    sleep "$WAIT_POST_STOP"
  fi

  echo "Deleting matched ECS services..."
  for service in "${matched_services[@]}"; do
    run_cmd "aws ${AWS_ARGS[*]} ecs delete-service --cluster \"$CLUSTER\" --service \"$service\" --force >/dev/null || true"
  done

  echo
}

delete_load_balancers() {
  echo "2) Load balancer cleanup"

  LB_INFO=$(aws "${AWS_ARGS[@]}" elbv2 describe-load-balancers --output json 2>/dev/null || true)

  MATCHED_LB_ARNS=$(echo "$LB_INFO" | jq -r --arg f "$NAME_FILTER" '
    (.LoadBalancers // [])
    | map(select((.LoadBalancerName // "") | contains($f)))
    | .[]
    | .LoadBalancerArn
  ')

  if [[ -n "${MATCHED_LB_ARNS:-}" ]]; then
    echo "Deleting matching load balancers..."
    while IFS= read -r lb_arn; do
      [[ -z "$lb_arn" ]] && continue
      run_cmd "aws ${AWS_ARGS[*]} elbv2 delete-load-balancer --load-balancer-arn \"$lb_arn\" || true"
    done <<< "$MATCHED_LB_ARNS"
  else
    echo "No matching load balancers found."
  fi

  if [[ "$DRY_RUN" -eq 0 ]]; then
    echo "Waiting ${WAIT_LB}s for load balancer deletion propagation..."
    sleep "$WAIT_LB"
  fi

  TG_INFO=$(aws "${AWS_ARGS[@]}" elbv2 describe-target-groups --output json 2>/dev/null || true)

  MATCHED_TG_ARNS=$(echo "$TG_INFO" | jq -r --arg f "$NAME_FILTER" '
    (.TargetGroups // [])
    | map(select((.TargetGroupName // "") | contains($f)))
    | .[]
    | .TargetGroupArn
  ')

  if [[ -n "${MATCHED_TG_ARNS:-}" ]]; then
    echo "Deleting matching target groups..."
    while IFS= read -r tg_arn; do
      [[ -z "$tg_arn" ]] && continue
      run_cmd "aws ${AWS_ARGS[*]} elbv2 delete-target-group --target-group-arn \"$tg_arn\" || true"
    done <<< "$MATCHED_TG_ARNS"
  else
    echo "No matching target groups found."
  fi

  echo
}

delete_network() {
  echo "3) Network cleanup (NAT gateways + EIPs)"

  NAT_INFO=$(aws "${AWS_ARGS[@]}" ec2 describe-nat-gateways --output json 2>/dev/null || true)
  MATCHED_NAT_IDS=$(echo "$NAT_INFO" | jq -r --arg f "$NAME_FILTER" '
    (.NatGateways // [])
    | map(select(
        ((.Tags // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ") | contains($f))
        or ((.NatGatewayId // "") | contains($f))
      ))
    | .[]
    | .NatGatewayId
  ')

  if [[ -n "${MATCHED_NAT_IDS:-}" ]]; then
    echo "Deleting matching NAT gateways..."
    while IFS= read -r nat_id; do
      [[ -z "$nat_id" ]] && continue
      run_cmd "aws ${AWS_ARGS[*]} ec2 delete-nat-gateway --nat-gateway-id \"$nat_id\" >/dev/null || true"
    done <<< "$MATCHED_NAT_IDS"
  else
    echo "No matching NAT gateways found."
  fi

  EIP_INFO=$(aws "${AWS_ARGS[@]}" ec2 describe-addresses --output json 2>/dev/null || true)
  MATCHED_EIP_ALLOC_IDS=$(echo "$EIP_INFO" | jq -r --arg f "$NAME_FILTER" '
    (.Addresses // [])
    | map(select(
        .AssociationId == null and
        (
          ((.Tags // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ") | contains($f))
          or ((.PublicIp // "") | contains($f))
          or ((.AllocationId // "") | contains($f))
        )
      ))
    | .[]
    | .AllocationId
  ')

  if [[ -n "${MATCHED_EIP_ALLOC_IDS:-}" ]]; then
    echo "Releasing matching unattached Elastic IPs..."
    while IFS= read -r allocation_id; do
      [[ -z "$allocation_id" ]] && continue
      run_cmd "aws ${AWS_ARGS[*]} ec2 release-address --allocation-id \"$allocation_id\" >/dev/null || true"
    done <<< "$MATCHED_EIP_ALLOC_IDS"
  else
    echo "No matching unattached Elastic IPs found."
  fi

  local specific_alloc specific_assoc
  specific_alloc=$(echo "$EIP_INFO" | jq -r --arg ip "$SPECIFIC_EIP_IP" '
    (.Addresses // []) | map(select((.PublicIp // "") == $ip)) | .[0].AllocationId // empty
  ')
  specific_assoc=$(echo "$EIP_INFO" | jq -r --arg ip "$SPECIFIC_EIP_IP" '
    (.Addresses // []) | map(select((.PublicIp // "") == $ip)) | .[0].AssociationId // empty
  ')

  if [[ -n "$specific_alloc" ]]; then
    if [[ -z "$specific_assoc" ]]; then
      echo "Releasing specific unattached Elastic IP ${SPECIFIC_EIP_IP} (${specific_alloc})"
      run_cmd "aws ${AWS_ARGS[*]} ec2 release-address --allocation-id \"$specific_alloc\" >/dev/null || true"
    else
      echo "Specific Elastic IP ${SPECIFIC_EIP_IP} is attached (${specific_assoc}); not releasing."
    fi
  else
    echo "Specific Elastic IP ${SPECIFIC_EIP_IP} not found in this region."
  fi

  echo
}

delete_waf() {
  echo "4) WAF cleanup (Web ACLs + associations + rules)"

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

    local waf_args=(--region "$waf_region")
    if [[ -n "$PROFILE" ]]; then
      waf_args+=(--profile "$PROFILE")
    fi

    WAF_INFO=$(aws "${waf_args[@]}" wafv2 list-web-acls --scope "$scope" --output json 2>/dev/null || true)
    local matched=0

    while IFS= read -r acl; do
      [[ -z "$acl" ]] && continue

      local acl_name acl_id acl_arn
      acl_name=$(echo "$acl" | jq -r '.Name')
      acl_id=$(echo "$acl" | jq -r '.Id')
      acl_arn=$(echo "$acl" | jq -r '.ARN')

      local tags_json tags_blob
      tags_json=$(aws "${waf_args[@]}" wafv2 list-tags-for-resource --resource-arn "$acl_arn" --output json 2>/dev/null || true)
      tags_blob=$(echo "${tags_json:-{\"TagInfoForResource\":{\"TagList\":[]}}}" | jq -r '(.TagInfoForResource.TagList // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ")')

      if ! contains_filter "$acl_name" && ! contains_filter "$tags_blob" && ! contains_filter "$acl_arn"; then
        continue
      fi

      matched=1
      echo "Matched WAF ACL: $acl_name ($scope)"

      for rt in "${resource_types[@]}"; do
        local resources
        resources=$(aws "${waf_args[@]}" wafv2 list-resources-for-web-acl \
          --web-acl-arn "$acl_arn" \
          --resource-type "$rt" \
          --query 'ResourceArns[]' \
          --output text 2>/dev/null || true)

        if [[ -n "${resources:-}" ]]; then
          for resource_arn in $resources; do
            run_cmd "aws ${waf_args[*]} wafv2 disassociate-web-acl --resource-arn \"$resource_arn\" >/dev/null || true"
          done
        fi
      done

      local lock_token
      lock_token=$(aws "${waf_args[@]}" wafv2 get-web-acl \
        --name "$acl_name" \
        --id "$acl_id" \
        --scope "$scope" \
        --query 'LockToken' \
        --output text 2>/dev/null || true)

      if [[ -z "${lock_token:-}" || "$lock_token" == "None" ]]; then
        echo "Unable to get lock token for ACL $acl_name; skipping delete."
        continue
      fi

      run_cmd "aws ${waf_args[*]} wafv2 delete-web-acl --name \"$acl_name\" --id \"$acl_id\" --scope \"$scope\" --lock-token \"$lock_token\" >/dev/null || true"
    done < <(echo "$WAF_INFO" | jq -c '.WebACLs[]?')

    if [[ "$matched" -eq 0 ]]; then
      echo "No matching WAF ACLs found for scope ${scope}."
    fi
  done

  echo
}

delete_kms() {
  echo "5) KMS cleanup (customer-managed keys)"

  KEY_IDS=$(aws "${AWS_ARGS[@]}" kms list-keys --query 'Keys[].KeyId' --output text 2>/dev/null || true)
  local matched=0

  if [[ -n "${KEY_IDS:-}" ]]; then
    for key_id in $KEY_IDS; do
      KEY_INFO=$(aws "${AWS_ARGS[@]}" kms describe-key --key-id "$key_id" --output json 2>/dev/null || true)
      [[ -z "${KEY_INFO:-}" ]] && continue

      local manager state arn description
      manager=$(echo "$KEY_INFO" | jq -r '.KeyMetadata.KeyManager // empty')
      state=$(echo "$KEY_INFO" | jq -r '.KeyMetadata.KeyState // empty')
      arn=$(echo "$KEY_INFO" | jq -r '.KeyMetadata.Arn // empty')
      description=$(echo "$KEY_INFO" | jq -r '.KeyMetadata.Description // empty')

      if [[ "$manager" != "CUSTOMER" ]]; then
        continue
      fi

      if [[ "$state" == "PendingDeletion" ]]; then
        continue
      fi

      local aliases tags alias_blob tag_blob match_text
      aliases=$(aws "${AWS_ARGS[@]}" kms list-aliases --key-id "$key_id" --output json 2>/dev/null || true)
      tags=$(aws "${AWS_ARGS[@]}" kms list-resource-tags --key-id "$key_id" --output json 2>/dev/null || true)

      alias_blob=$(echo "${aliases:-{\"Aliases\":[]}}" | jq -r '(.Aliases // []) | map(.AliasName // "") | join(" ")')
      tag_blob=$(echo "${tags:-{\"Tags\":[]}}" | jq -r '(.Tags // []) | map((.TagKey // "") + "=" + (.TagValue // "")) | join(" ")')
      match_text="$arn $description $alias_blob $tag_blob"

      if ! contains_filter "$match_text"; then
        continue
      fi

      matched=1
      echo "Matched KMS key: ${arn:-$key_id}"
      run_cmd "aws ${AWS_ARGS[*]} kms disable-key --key-id \"$key_id\" >/dev/null 2>&1 || true"
      run_cmd "aws ${AWS_ARGS[*]} kms schedule-key-deletion --key-id \"$key_id\" --pending-window-in-days 7 >/dev/null || true"
    done
  fi

  if [[ "$matched" -eq 0 ]]; then
    echo "No matching customer-managed KMS keys found."
  fi

  echo
}

delete_storage() {
  echo "6) Storage cleanup (AMIs + EBS snapshots)"

  IMAGE_INFO=$(aws "${AWS_ARGS[@]}" ec2 describe-images --owners self --output json 2>/dev/null || true)

  MATCHED_IMAGE_IDS=$(echo "$IMAGE_INFO" | jq -r --arg f "$NAME_FILTER" '
    (.Images // [])
    | map(select(
        ((.ImageId // "") | contains($f))
        or ((.Name // "") | contains($f))
        or ((.Description // "") | contains($f))
        or (((.Tags // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ")) | contains($f))
      ))
    | .[]
    | .ImageId
  ')

  MATCHED_IMAGE_SNAPSHOTS=$(echo "$IMAGE_INFO" | jq -r --arg f "$NAME_FILTER" '
    (.Images // [])
    | map(select(
        ((.ImageId // "") | contains($f))
        or ((.Name // "") | contains($f))
        or ((.Description // "") | contains($f))
        or (((.Tags // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ")) | contains($f))
      ))
    | .[]
    | .BlockDeviceMappings[]?.Ebs?.SnapshotId // empty
  ' | sort -u)

  if [[ -n "${MATCHED_IMAGE_IDS:-}" ]]; then
    echo "Deregistering matching AMIs..."
    while IFS= read -r image_id; do
      [[ -z "$image_id" ]] && continue
      run_cmd "aws ${AWS_ARGS[*]} ec2 deregister-image --image-id \"$image_id\" >/dev/null || true"
    done <<< "$MATCHED_IMAGE_IDS"
  else
    echo "No matching AMIs found."
  fi

  if [[ -n "${MATCHED_IMAGE_SNAPSHOTS:-}" ]]; then
    echo "Deleting snapshots associated with matching AMIs..."
    while IFS= read -r snap_id; do
      [[ -z "$snap_id" ]] && continue
      run_cmd "aws ${AWS_ARGS[*]} ec2 delete-snapshot --snapshot-id \"$snap_id\" >/dev/null || true"
    done <<< "$MATCHED_IMAGE_SNAPSHOTS"
  fi

  SNAPSHOT_INFO=$(aws "${AWS_ARGS[@]}" ec2 describe-snapshots --owner-ids self --output json 2>/dev/null || true)
  MATCHED_SNAPSHOTS=$(echo "$SNAPSHOT_INFO" | jq -r --arg f "$NAME_FILTER" '
    (.Snapshots // [])
    | map(select(
        ((.SnapshotId // "") | contains($f))
        or ((.Description // "") | contains($f))
        or (((.Tags // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ")) | contains($f))
      ))
    | .[]
    | .SnapshotId
  ')

  if [[ -n "${MATCHED_SNAPSHOTS:-}" ]]; then
    echo "Deleting matching snapshots..."
    while IFS= read -r snapshot_id; do
      [[ -z "$snapshot_id" ]] && continue
      run_cmd "aws ${AWS_ARGS[*]} ec2 delete-snapshot --snapshot-id \"$snapshot_id\" >/dev/null || true"
    done <<< "$MATCHED_SNAPSHOTS"
  else
    echo "No additional matching snapshots found."
  fi

  echo
}

delete_ecr() {
  echo "7) ECR cleanup"

  REPOS=$(aws "${AWS_ARGS[@]}" ecr describe-repositories \
    --query 'repositories[].repositoryName' \
    --output text 2>/dev/null || true)

  local found=0
  if [[ -n "${REPOS:-}" ]]; then
    for repo in $REPOS; do
      if contains_filter "$repo"; then
        found=1
        run_cmd "aws ${AWS_ARGS[*]} ecr delete-repository --repository-name \"$repo\" --force || true"
      fi
    done
  fi

  if [[ "$found" -eq 0 ]]; then
    echo "No matching ECR repositories found."
  fi

  echo
}

delete_log_groups() {
  echo "8) CloudWatch log group cleanup"

  LOG_GROUPS=$(aws "${AWS_ARGS[@]}" logs describe-log-groups \
    --query 'logGroups[].logGroupName' \
    --output text 2>/dev/null || true)

  local found=0
  if [[ -n "${LOG_GROUPS:-}" ]]; then
    for lg in $LOG_GROUPS; do
      if contains_filter "$lg"; then
        found=1
        run_cmd "aws ${AWS_ARGS[*]} logs delete-log-group --log-group-name \"$lg\" || true"
      fi
    done
  fi

  if [[ "$found" -eq 0 ]]; then
    echo "No matching log groups found."
  fi

  echo
}

show_remaining() {
  echo "9) Remaining matching resources"

  echo "--- ECS services ---"
  aws "${AWS_ARGS[@]}" ecs list-services \
    --cluster "$CLUSTER" \
    --output text 2>/dev/null || true

  echo "--- Load balancers ---"
  aws "${AWS_ARGS[@]}" elbv2 describe-load-balancers \
    --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
      (.LoadBalancers // [])
      | map(select((.LoadBalancerName // "") | contains($f)))
      | .[]
      | .LoadBalancerName + "  " + .LoadBalancerArn
    ' || true

  echo "--- Target groups ---"
  aws "${AWS_ARGS[@]}" elbv2 describe-target-groups \
    --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
      (.TargetGroups // [])
      | map(select((.TargetGroupName // "") | contains($f)))
      | .[]
      | .TargetGroupName + "  " + .TargetGroupArn
    ' || true

  echo "--- NAT gateways ---"
  aws "${AWS_ARGS[@]}" ec2 describe-nat-gateways \
    --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
      (.NatGateways // [])
      | map(select(
          ((.Tags // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ") | contains($f))
          or ((.NatGatewayId // "") | contains($f))
      ))
      | .[]
      | .NatGatewayId
    ' || true

  echo "--- Unattached Elastic IPs matching filter ---"
  aws "${AWS_ARGS[@]}" ec2 describe-addresses \
    --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
      (.Addresses // [])
      | map(select(
          .AssociationId == null and
          (
            ((.Tags // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ") | contains($f))
            or ((.PublicIp // "") | contains($f))
            or ((.AllocationId // "") | contains($f))
          )
      ))
      | .[]
      | .PublicIp + "  " + .AllocationId
    ' || true

  echo "--- Specific Elastic IP ---"
  aws "${AWS_ARGS[@]}" ec2 describe-addresses \
    --public-ips "$SPECIFIC_EIP_IP" \
    --query 'Addresses[].{PublicIp:PublicIp,AllocationId:AllocationId,AssociationId:AssociationId}' \
    --output table 2>/dev/null || true

  echo "--- WAF Web ACLs (matching filter, REGIONAL) ---"
  aws "${AWS_ARGS[@]}" wafv2 list-web-acls --scope REGIONAL --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
    (.WebACLs // [])
    | map(select((.Name // "") | contains($f)))
    | .[]
    | .Name + "  " + .ARN
  ' || true

  echo "--- WAF Web ACLs (matching filter, CLOUDFRONT/us-east-1) ---"
  local cf_args=(--region us-east-1)
  if [[ -n "$PROFILE" ]]; then
    cf_args+=(--profile "$PROFILE")
  fi
  aws "${cf_args[@]}" wafv2 list-web-acls --scope CLOUDFRONT --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
    (.WebACLs // [])
    | map(select((.Name // "") | contains($f)))
    | .[]
    | .Name + "  " + .ARN
  ' || true

  echo "--- KMS customer keys matching filter (not pending deletion) ---"
  KEY_IDS=$(aws "${AWS_ARGS[@]}" kms list-keys --query 'Keys[].KeyId' --output text 2>/dev/null || true)
  if [[ -n "${KEY_IDS:-}" ]]; then
    for key_id in $KEY_IDS; do
      KEY_INFO=$(aws "${AWS_ARGS[@]}" kms describe-key --key-id "$key_id" --output json 2>/dev/null || true)
      [[ -z "${KEY_INFO:-}" ]] && continue

      local manager state arn description aliases tags alias_blob tag_blob combined
      manager=$(echo "$KEY_INFO" | jq -r '.KeyMetadata.KeyManager // empty')
      state=$(echo "$KEY_INFO" | jq -r '.KeyMetadata.KeyState // empty')
      arn=$(echo "$KEY_INFO" | jq -r '.KeyMetadata.Arn // empty')
      description=$(echo "$KEY_INFO" | jq -r '.KeyMetadata.Description // empty')
      [[ "$manager" != "CUSTOMER" || "$state" == "PendingDeletion" ]] && continue

      aliases=$(aws "${AWS_ARGS[@]}" kms list-aliases --key-id "$key_id" --output json 2>/dev/null || true)
      tags=$(aws "${AWS_ARGS[@]}" kms list-resource-tags --key-id "$key_id" --output json 2>/dev/null || true)
      alias_blob=$(echo "${aliases:-{\"Aliases\":[]}}" | jq -r '(.Aliases // []) | map(.AliasName // "") | join(" ")')
      tag_blob=$(echo "${tags:-{\"Tags\":[]}}" | jq -r '(.Tags // []) | map((.TagKey // "") + "=" + (.TagValue // "")) | join(" ")')
      combined="$arn $description $alias_blob $tag_blob"

      if contains_filter "$combined"; then
        echo "$arn"
      fi
    done
  fi

  echo "--- AMIs matching filter ---"
  aws "${AWS_ARGS[@]}" ec2 describe-images --owners self --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
    (.Images // [])
    | map(select(
        ((.ImageId // "") | contains($f))
        or ((.Name // "") | contains($f))
        or ((.Description // "") | contains($f))
        or (((.Tags // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ")) | contains($f))
      ))
    | .[]
    | (.ImageId + "  " + (.Name // ""))
  ' || true

  echo "--- Snapshots matching filter ---"
  aws "${AWS_ARGS[@]}" ec2 describe-snapshots --owner-ids self --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
    (.Snapshots // [])
    | map(select(
        ((.SnapshotId // "") | contains($f))
        or ((.Description // "") | contains($f))
        or (((.Tags // []) | map((.Key // "") + "=" + (.Value // "")) | join(" ")) | contains($f))
      ))
    | .[]
    | (.SnapshotId + "  " + (.Description // ""))
  ' || true

  echo "--- ECR repositories ---"
  aws "${AWS_ARGS[@]}" ecr describe-repositories \
    --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
      (.repositories // [])
      | map(select((.repositoryName // "") | contains($f)))
      | .[]
      | .repositoryName
    ' || true

  echo "--- Log groups ---"
  aws "${AWS_ARGS[@]}" logs describe-log-groups \
    --output json 2>/dev/null | jq -r --arg f "$NAME_FILTER" '
      (.logGroups // [])
      | map(select((.logGroupName // "") | contains($f)))
      | .[]
      | .logGroupName
    ' || true
}

[[ "$DELETE_ECS" -eq 1 ]] && delete_ecs
[[ "$DELETE_LOAD_BALANCERS" -eq 1 ]] && delete_load_balancers
[[ "$DELETE_NETWORK" -eq 1 ]] && delete_network
[[ "$DELETE_WAF" -eq 1 ]] && delete_waf
[[ "$DELETE_KMS" -eq 1 ]] && delete_kms
[[ "$DELETE_STORAGE" -eq 1 ]] && delete_storage
[[ "$DELETE_ECR" -eq 1 ]] && delete_ecr
[[ "$DELETE_LOG_GROUPS" -eq 1 ]] && delete_log_groups

show_remaining

echo
echo "=== Targeted cleanup finished ==="
