#!/usr/bin/env bash
set -euo pipefail

REGION="eu-central-1"
CLUSTER="decoration-preview-cluster"

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
echo "5) Delete load balancers"
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
echo "6) Delete target groups"
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
echo "7) Delete ECR repositories and images"
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
echo "8) Delete CloudWatch log groups"
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
echo "9) Optional: list remaining cost-relevant resources"
echo "--- ECS clusters ---"
aws ecs list-clusters --region "$REGION" || true

echo "--- Load balancers ---"
aws elbv2 describe-load-balancers --region "$REGION" || true

echo "--- ECR repos ---"
aws ecr describe-repositories --region "$REGION" || true

echo "--- Log groups ---"
aws logs describe-log-groups --region "$REGION" || true

echo
echo "=== Cleanup finished ==="
