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
      A KMS audit report runs automatically before any deletion.

  --audit-kms, --report-kms
      Run KMS audit/report mode only (no deletion). Lists customer-managed keys,
      usage across EBS/S3/RDS resources, and keys that appear safe to delete.

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
AUDIT_KMS=0
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
    --audit-kms|--report-kms)
      AUDIT_KMS=1
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

declare -a KMS_AUDIT_KEY_IDS=()
declare -A KMS_AUDIT_KEY_ARN=()
declare -A KMS_AUDIT_KEY_STATE=()
declare -A KMS_AUDIT_KEY_CREATED=()
declare -A KMS_AUDIT_KEY_DESCRIPTION=()
declare -A KMS_AUDIT_KEY_ALIASES=()
declare -A KMS_AUDIT_KEY_USAGE=()
declare -A KMS_AUDIT_KEY_SAFE_TO_DELETE=()
declare -A KMS_AUDIT_KEY_MATCHES_FILTER=()
KMS_AUDIT_BUILT=0

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
echo "Audit/report KMS only:  $AUDIT_KMS"
echo "Delete ECR:             $DELETE_ECR"
echo "Delete log groups:      $DELETE_LOG_GROUPS"
echo "Dry run:                $DRY_RUN"
echo

HAS_DELETE_ACTION=0
if [[ "$DELETE_ECS" -eq 1 || "$DELETE_LOAD_BALANCERS" -eq 1 || "$DELETE_NETWORK" -eq 1 || "$DELETE_WAF" -eq 1 || "$DELETE_KMS" -eq 1 || "$DELETE_STORAGE" -eq 1 || "$DELETE_ECR" -eq 1 || "$DELETE_LOG_GROUPS" -eq 1 ]]; then
  HAS_DELETE_ACTION=1
fi

if [[ "$HAS_DELETE_ACTION" -eq 0 && "$AUDIT_KMS" -eq 0 ]]; then
  echo "Nothing selected."
  echo "Use one of: --audit-kms/--report-kms, --delete-ecs, --delete-load-balancers, --delete-network, --delete-waf, --delete-kms, --delete-storage, --delete-ecr, --delete-log-groups, or --delete-all"
  exit 1
fi

if [[ "$HAS_DELETE_ACTION" -eq 1 && "$FORCE" -eq 0 && "$DRY_RUN" -eq 0 ]]; then
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

kms_normalize_identifier() {
  local raw="${1:-}"
  echo "${raw,,}"
}

kms_identifier_matches_key() {
  local key_id="${1:-}"
  local key_arn="${2:-}"
  local aliases_blob="${3:-}"
  local candidate="${4:-}"

  [[ -z "$candidate" ]] && return 1

  local c_norm key_id_norm key_arn_norm
  c_norm=$(kms_normalize_identifier "$candidate")
  key_id_norm=$(kms_normalize_identifier "$key_id")
  key_arn_norm=$(kms_normalize_identifier "$key_arn")

  if [[ "$c_norm" == "$key_id_norm" || "$c_norm" == "$key_arn_norm" ]]; then
    return 0
  fi

  local arn_prefix alias alias_norm alias_arn_norm
  arn_prefix="${key_arn%:key/*}"

  for alias in $aliases_blob; do
    alias_norm=$(kms_normalize_identifier "$alias")
    alias_arn_norm=$(kms_normalize_identifier "${arn_prefix}:$alias")
    if [[ "$c_norm" == "$alias_norm" || "$c_norm" == "$alias_arn_norm" ]]; then
      return 0
    fi
  done

  return 1
}

build_kms_audit_data() {
  if [[ "$KMS_AUDIT_BUILT" -eq 1 ]]; then
    return
  fi

  KMS_AUDIT_KEY_IDS=()

  local key_ids
  key_ids=$(aws "${AWS_ARGS[@]}" kms list-keys --query 'Keys[].KeyId' --output text 2>/dev/null || true)

  if [[ -z "${key_ids:-}" ]]; then
    KMS_AUDIT_BUILT=1
    return
  fi

  local volumes_json snapshots_json db_instances_json db_clusters_json bucket_names
  volumes_json=$(aws "${AWS_ARGS[@]}" ec2 describe-volumes --output json 2>/dev/null || true)
  snapshots_json=$(aws "${AWS_ARGS[@]}" ec2 describe-snapshots --owner-ids self --output json 2>/dev/null || true)
  db_instances_json=$(aws "${AWS_ARGS[@]}" rds describe-db-instances --output json 2>/dev/null || true)
  db_clusters_json=$(aws "${AWS_ARGS[@]}" rds describe-db-clusters --output json 2>/dev/null || true)
  bucket_names=$(aws "${AWS_ARGS[@]}" s3api list-buckets --query 'Buckets[].Name' --output text 2>/dev/null || true)

  local key_id key_info manager state arn created description aliases_json tags_json alias_blob tag_blob combined
  for key_id in $key_ids; do
    key_info=$(aws "${AWS_ARGS[@]}" kms describe-key --key-id "$key_id" --output json 2>/dev/null || true)
    [[ -z "${key_info:-}" ]] && continue

    manager=$(echo "$key_info" | jq -r '.KeyMetadata.KeyManager // empty')
    [[ "$manager" != "CUSTOMER" ]] && continue

    state=$(echo "$key_info" | jq -r '.KeyMetadata.KeyState // "unknown"')
    arn=$(echo "$key_info" | jq -r '.KeyMetadata.Arn // empty')
    created=$(echo "$key_info" | jq -r '.KeyMetadata.CreationDate // "unknown"')
    description=$(echo "$key_info" | jq -r '.KeyMetadata.Description // ""')

    aliases_json=$(aws "${AWS_ARGS[@]}" kms list-aliases --key-id "$key_id" --output json 2>/dev/null || true)
    tags_json=$(aws "${AWS_ARGS[@]}" kms list-resource-tags --key-id "$key_id" --output json 2>/dev/null || true)
    alias_blob=$(echo "${aliases_json:-{\"Aliases\":[]}}" | jq -r '(.Aliases // []) | map(.AliasName // "") | map(select(length > 0)) | join(" ")')
    tag_blob=$(echo "${tags_json:-{\"Tags\":[]}}" | jq -r '(.Tags // []) | map((.TagKey // "") + "=" + (.TagValue // "")) | join(" ")')

    local usage_lines=()
    local vol_hits=()
    local snap_hits=()
    local rds_hits=()
    local rds_cluster_hits=()
    local s3_hits=()

    while IFS=$'        ' read -r kms_id volume_id volume_state; do
      [[ -z "${volume_id:-}" ]] && continue
      if kms_identifier_matches_key "$key_id" "$arn" "$alias_blob" "$kms_id"; then
        vol_hits+=("${volume_id}(${volume_state:-unknown})")
      fi
    done < <(echo "${volumes_json:-{\"Volumes\":[]}}" | jq -r '.Volumes[]? | select(.Encrypted == true) | [(.KmsKeyId // ""), (.VolumeId // ""), (.State // "")] | @tsv')

    while IFS=$'        ' read -r kms_id snapshot_id snapshot_state; do
      [[ -z "${snapshot_id:-}" ]] && continue
      if kms_identifier_matches_key "$key_id" "$arn" "$alias_blob" "$kms_id"; then
        snap_hits+=("${snapshot_id}(${snapshot_state:-unknown})")
      fi
    done < <(echo "${snapshots_json:-{\"Snapshots\":[]}}" | jq -r '.Snapshots[]? | select(.Encrypted == true) | [(.KmsKeyId // ""), (.SnapshotId // ""), (.State // "")] | @tsv')

    while IFS=$'        ' read -r kms_id db_id db_state; do
      [[ -z "${db_id:-}" ]] && continue
      if kms_identifier_matches_key "$key_id" "$arn" "$alias_blob" "$kms_id"; then
        rds_hits+=("${db_id}(${db_state:-unknown})")
      fi
    done < <(echo "${db_instances_json:-{\"DBInstances\":[]}}" | jq -r '.DBInstances[]? | [(.KmsKeyId // ""), (.DBInstanceIdentifier // ""), (.DBInstanceStatus // "")] | @tsv')

    while IFS=$'        ' read -r kms_id cluster_id cluster_state; do
      [[ -z "${cluster_id:-}" ]] && continue
      if kms_identifier_matches_key "$key_id" "$arn" "$alias_blob" "$kms_id"; then
        rds_cluster_hits+=("${cluster_id}(${cluster_state:-unknown})")
      fi
    done < <(echo "${db_clusters_json:-{\"DBClusters\":[]}}" | jq -r '.DBClusters[]? | [(.KmsKeyId // ""), (.DBClusterIdentifier // ""), (.Status // "")] | @tsv')

    if [[ -n "${bucket_names:-}" ]]; then
      local bucket enc_json bucket_kms_id
      for bucket in $bucket_names; do
        enc_json=$(aws "${AWS_ARGS[@]}" s3api get-bucket-encryption --bucket "$bucket" --output json 2>/dev/null || true)
        [[ -z "${enc_json:-}" ]] && continue
        while IFS= read -r bucket_kms_id; do
          [[ -z "${bucket_kms_id:-}" ]] && continue
          if kms_identifier_matches_key "$key_id" "$arn" "$alias_blob" "$bucket_kms_id"; then
            s3_hits+=("$bucket")
            break
          fi
        done < <(echo "$enc_json" | jq -r '.ServerSideEncryptionConfiguration.Rules[]?.ApplyServerSideEncryptionByDefault.KMSMasterKeyID // empty')
      done
    fi

    if [[ ${#vol_hits[@]} -gt 0 ]]; then
      usage_lines+=("EBS volumes: ${vol_hits[*]}")
    fi
    if [[ ${#snap_hits[@]} -gt 0 ]]; then
      usage_lines+=("EBS snapshots: ${snap_hits[*]}")
    fi
    if [[ ${#s3_hits[@]} -gt 0 ]]; then
      usage_lines+=("S3 buckets: ${s3_hits[*]}")
    fi
    if [[ ${#rds_hits[@]} -gt 0 ]]; then
      usage_lines+=("RDS instances: ${rds_hits[*]}")
    fi
    if [[ ${#rds_cluster_hits[@]} -gt 0 ]]; then
      usage_lines+=("RDS clusters: ${rds_cluster_hits[*]}")
    fi

    local safe_to_delete=0
    if [[ ${#usage_lines[@]} -eq 0 && "$state" != "PendingDeletion" ]]; then
      safe_to_delete=1
    fi

    combined="$arn $description $alias_blob $tag_blob"

    KMS_AUDIT_KEY_IDS+=("$key_id")
    KMS_AUDIT_KEY_ARN["$key_id"]="$arn"
    KMS_AUDIT_KEY_STATE["$key_id"]="$state"
    KMS_AUDIT_KEY_CREATED["$key_id"]="$created"
    KMS_AUDIT_KEY_DESCRIPTION["$key_id"]="$description"
    KMS_AUDIT_KEY_ALIASES["$key_id"]="$alias_blob"
    KMS_AUDIT_KEY_USAGE["$key_id"]="$(printf '%s; ' "${usage_lines[@]}")"
    KMS_AUDIT_KEY_SAFE_TO_DELETE["$key_id"]="$safe_to_delete"

    if contains_filter "$combined"; then
      KMS_AUDIT_KEY_MATCHES_FILTER["$key_id"]=1
    else
      KMS_AUDIT_KEY_MATCHES_FILTER["$key_id"]=0
    fi
  done

  KMS_AUDIT_BUILT=1
}

print_kms_audit_report() {
  build_kms_audit_data

  echo "5) KMS audit report (customer-managed keys)"

  if [[ ${#KMS_AUDIT_KEY_IDS[@]} -eq 0 ]]; then
    echo "No customer-managed KMS keys found in region ${REGION}."
    echo
    return
  fi

  local total=0 safe_count=0 in_use_count=0
  for key_id in "${KMS_AUDIT_KEY_IDS[@]}"; do
    total=$((total + 1))

    local arn state created description aliases usage safe matches_filter
    arn="${KMS_AUDIT_KEY_ARN[$key_id]}"
    state="${KMS_AUDIT_KEY_STATE[$key_id]}"
    created="${KMS_AUDIT_KEY_CREATED[$key_id]}"
    description="${KMS_AUDIT_KEY_DESCRIPTION[$key_id]}"
    aliases="${KMS_AUDIT_KEY_ALIASES[$key_id]}"
    usage="${KMS_AUDIT_KEY_USAGE[$key_id]}"
    safe="${KMS_AUDIT_KEY_SAFE_TO_DELETE[$key_id]}"
    matches_filter="${KMS_AUDIT_KEY_MATCHES_FILTER[$key_id]}"

    if [[ "$safe" -eq 1 ]]; then
      safe_count=$((safe_count + 1))
    else
      in_use_count=$((in_use_count + 1))
    fi

    echo "- Key: ${arn:-$key_id}"
    echo "  KeyId:        $key_id"
    echo "  Status:       $state"
    echo "  Created:      $created"
    echo "  Description:  ${description:-<none>}"
    echo "  Aliases:      ${aliases:-<none>}"
    echo "  Filter match: $matches_filter"

    if [[ -n "${usage// }" ]]; then
      echo "  Usage:"
      local usage_line
      IFS=';' read -ra usage_parts <<< "$usage"
      for usage_line in "${usage_parts[@]}"; do
        usage_line="${usage_line# }"
        usage_line="${usage_line% }"
        [[ -z "$usage_line" ]] && continue
        echo "    - $usage_line"
      done
      echo "  Safe to delete: NO (resource usage detected)"
    elif [[ "$state" == "PendingDeletion" ]]; then
      echo "  Usage:         none detected in audited services"
      echo "  Safe to delete: NO (already pending deletion)"
    else
      echo "  Usage:         none detected in audited services"
      echo "  Safe to delete: YES (based on audited services)"
    fi
    echo
  done

  echo "KMS audit summary:"
  echo "  Total customer-managed keys: $total"
  echo "  Safe to delete candidates:   $safe_count"
  echo "  Not safe / in use:           $in_use_count"
  echo
}

delete_kms() {
  echo "6) KMS cleanup (customer-managed keys)"

  build_kms_audit_data

  local matched=0 scheduled=0 skipped_in_use=0

  for key_id in "${KMS_AUDIT_KEY_IDS[@]}"; do
    local arn state usage safe matches_filter
    arn="${KMS_AUDIT_KEY_ARN[$key_id]}"
    state="${KMS_AUDIT_KEY_STATE[$key_id]}"
    usage="${KMS_AUDIT_KEY_USAGE[$key_id]}"
    safe="${KMS_AUDIT_KEY_SAFE_TO_DELETE[$key_id]}"
    matches_filter="${KMS_AUDIT_KEY_MATCHES_FILTER[$key_id]}"

    [[ "$matches_filter" -eq 1 ]] || continue
    matched=1

    if [[ "$state" == "PendingDeletion" ]]; then
      echo "Skipping ${arn:-$key_id}: already pending deletion."
      continue
    fi

    if [[ "$safe" -ne 1 ]]; then
      skipped_in_use=$((skipped_in_use + 1))
      echo "Skipping ${arn:-$key_id}: key appears in use."
      if [[ -n "${usage// }" ]]; then
        echo "  Usage summary: $usage"
      fi
      continue
    fi

    echo "Scheduling deletion for ${arn:-$key_id} (safe candidate, 7-day window)"
    run_cmd "aws ${AWS_ARGS[*]} kms disable-key --key-id \"$key_id\" >/dev/null 2>&1 || true"
    run_cmd "aws ${AWS_ARGS[*]} kms schedule-key-deletion --key-id \"$key_id\" --pending-window-in-days 7 >/dev/null || true"
    scheduled=$((scheduled + 1))
  done

  if [[ "$matched" -eq 0 ]]; then
    echo "No matching customer-managed KMS keys found for filter '$NAME_FILTER'."
  else
    echo "KMS deletion summary: scheduled=$scheduled, skipped_in_use_or_not_safe=$skipped_in_use"
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

if [[ "$HAS_DELETE_ACTION" -eq 1 || "$AUDIT_KMS" -eq 1 ]]; then
  print_kms_audit_report
fi

if [[ "$HAS_DELETE_ACTION" -eq 0 && "$AUDIT_KMS" -eq 1 ]]; then
  echo "Audit-only mode selected; no deletion actions were run."
  echo
  echo "=== Targeted cleanup finished ==="
  exit 0
fi

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
