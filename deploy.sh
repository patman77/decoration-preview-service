#!/usr/bin/env bash
# ============================================================
# Decoration Preview Service - AWS CDK Deployment Script
# ============================================================
# Usage:
#   ./deploy.sh [command] [options]
#
# Commands:
#   bootstrap  - Bootstrap CDK in your AWS account (first time only)
#   synth      - Synthesize CloudFormation templates (dry run)
#   deploy     - Deploy all stacks to AWS
#   deploy-stack <name> - Deploy a specific stack
#   destroy    - Destroy all stacks (CAUTION!)
#   cleanup    - Delete stacks stuck in ROLLBACK_COMPLETE state
#   status     - Show deployment status and stack outputs
#   diff       - Show pending changes before deploy
# ============================================================

set -euo pipefail

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INFRA_DIR="${SCRIPT_DIR}/infrastructure"

# Default values
AWS_REGION="${AWS_REGION:-eu-central-1}"
ENVIRONMENT="${ENVIRONMENT:-production}"

# Timeout for potentially hanging commands (seconds)
CHECK_TIMEOUT="${CHECK_TIMEOUT:-15}"

log_info()  { echo -e "${BLUE}[INFO]${NC}  $*"; }
log_ok()    { echo -e "${GREEN}[OK]${NC}    $*"; }
log_warn()  { echo -e "${YELLOW}[WARN]${NC}  $*"; }
log_error() { echo -e "${RED}[ERROR]${NC} $*"; }
log_debug() { echo -e "${CYAN}[DEBUG]${NC} $*"; }

# Run a command with a timeout to prevent silent hangs
run_with_timeout() {
    local timeout_secs="$1"
    shift
    local description="$1"
    shift

    if command -v timeout &> /dev/null; then
        if ! timeout "${timeout_secs}" "$@" 2>/tmp/deploy_timeout_err; then
            local exit_code=$?
            if [ $exit_code -eq 124 ]; then
                log_error "${description} timed out after ${timeout_secs}s"
                log_error "Command: $*"
                log_error "This usually means the service is not responding. Check if it's running."
            else
                log_error "${description} failed (exit code: ${exit_code})"
                log_error "stderr: $(cat /tmp/deploy_timeout_err 2>/dev/null)"
            fi
            return 1
        fi
    else
        # Fallback: run without timeout but warn
        log_warn "timeout command not available, running '${description}' without timeout guard..."
        if ! "$@" 2>/tmp/deploy_timeout_err; then
            log_error "${description} failed"
            log_error "stderr: $(cat /tmp/deploy_timeout_err 2>/dev/null)"
            return 1
        fi
    fi
    return 0
}

# ── Pre-flight checks ──────────────────────────────────────
check_prerequisites() {
    log_info "Running pre-flight checks..."

    # AWS CLI
    if ! command -v aws &> /dev/null; then
        log_error "AWS CLI not found. Install: https://docs.aws.amazon.com/cli/latest/userguide/install-cliv2.html"
        exit 1
    fi
    log_ok "AWS CLI found: $(aws --version 2>&1 | head -1)"

    # AWS credentials
    if ! aws sts get-caller-identity &> /dev/null; then
        log_error "AWS credentials not configured. Run: aws configure"
        exit 1
    fi
    AWS_ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
    log_ok "AWS Account: ${AWS_ACCOUNT_ID}"

    # CDK CLI
    if ! command -v cdk &> /dev/null; then
        log_error "AWS CDK CLI not found. Install: npm install -g aws-cdk"
        exit 1
    fi
    log_ok "CDK CLI found: $(cdk --version)"

    # Docker
    log_debug "Checking for Docker binary..."
    if ! command -v docker &> /dev/null; then
        log_error "Docker not found. Install: https://docs.docker.com/get-docker/"
        exit 1
    fi
    log_debug "Docker binary found at: $(command -v docker). Checking Docker daemon (timeout: ${CHECK_TIMEOUT}s)..."
    if ! run_with_timeout "${CHECK_TIMEOUT}" "Docker daemon check" docker info > /dev/null; then
        log_error "Docker daemon is not running or not responding within ${CHECK_TIMEOUT}s."
        log_error "Troubleshooting:"
        log_error "  - macOS: Open Docker Desktop and wait for it to fully start"
        log_error "  - Linux: Run 'sudo systemctl start docker' or 'sudo service docker start'"
        log_error "  - Permission issue? Try: 'sudo docker info' or add user to docker group"
        log_error "  - Increase timeout: CHECK_TIMEOUT=30 ./deploy.sh bootstrap"
        exit 1
    fi
    log_ok "Docker found and running: $(docker --version)"

    # Python
    log_debug "Checking for Python..."
    if ! command -v python3 &> /dev/null; then
        log_error "Python 3 not found."
        exit 1
    fi
    log_ok "Python found: $(python3 --version)"

    # Node.js (needed for CDK)
    log_debug "Checking for Node.js..."
    if ! command -v node &> /dev/null; then
        log_error "Node.js not found. CDK requires Node.js. Install: https://nodejs.org/"
        exit 1
    fi
    log_ok "Node.js found: $(node --version)"

    echo ""
    log_ok "All pre-flight checks passed!"
}

# ── Install Python dependencies ────────────────────────────
install_deps() {
    log_info "Installing Python dependencies..."
    if [ ! -d "${SCRIPT_DIR}/venv" ]; then
        log_debug "Creating virtual environment at ${SCRIPT_DIR}/venv ..."
        python3 -m venv "${SCRIPT_DIR}/venv"
    else
        log_debug "Virtual environment already exists."
    fi
    source "${SCRIPT_DIR}/venv/bin/activate"
    log_debug "Running pip install (this may take a minute on first run)..."
    pip install -r "${SCRIPT_DIR}/requirements.txt" 2>&1 | while IFS= read -r line; do
        # Show progress dots for quiet installs, full output for new installs
        if [[ "$line" == *"already satisfied"* ]]; then
            printf "."
        else
            echo "  $line"
        fi
    done
    echo ""  # newline after dots
    log_ok "Dependencies installed."
}

# ── Update cdk.json with real account ──────────────────────
update_cdk_config() {
    local account_id
    account_id=$(aws sts get-caller-identity --query Account --output text)
    log_info "Updating cdk.json with account ${account_id} and region ${AWS_REGION}..."

    cat > "${INFRA_DIR}/cdk.json" <<EOF
{
  "app": "python3 app.py",
  "context": {
    "account": "${account_id}",
    "region": "${AWS_REGION}",
    "environment": "${ENVIRONMENT}"
  }
}
EOF
    log_ok "cdk.json updated."
}

# ── Cleanup failed stacks ───────────────────────────────────
cmd_cleanup() {
    log_info "Scanning for failed stacks in ROLLBACK_COMPLETE state..."
    local stacks=(
        "decoration-preview-monitoring"
        "decoration-preview-api"
        "decoration-preview-compute"
        "decoration-preview-storage"
        "decoration-preview-network"
    )

    local found_failed=false
    for stack in "${stacks[@]}"; do
        local status
        status=$(aws cloudformation describe-stacks \
            --stack-name "${stack}" \
            --query 'Stacks[0].StackStatus' \
            --output text \
            --region "${AWS_REGION}" 2>/dev/null) || continue

        if [[ "$status" == "ROLLBACK_COMPLETE" || "$status" == "CREATE_FAILED" || "$status" == "DELETE_FAILED" ]]; then
            found_failed=true
            log_warn "Stack ${stack} is in ${status} state."
            read -rp "  Delete this stack? [y/N] " confirm
            if [[ "$confirm" =~ ^[yY]$ ]]; then
                log_info "Deleting stack ${stack}..."
                if aws cloudformation delete-stack --stack-name "${stack}" --region "${AWS_REGION}"; then
                    log_info "Waiting for ${stack} deletion to complete..."
                    aws cloudformation wait stack-delete-complete \
                        --stack-name "${stack}" \
                        --region "${AWS_REGION}" 2>/dev/null && \
                        log_ok "Stack ${stack} deleted." || \
                        log_error "Stack ${stack} deletion may have failed. Check the AWS Console."
                else
                    log_error "Failed to initiate deletion of ${stack}."
                fi
            else
                log_info "Skipping ${stack}."
            fi
        elif [[ "$status" == "ROLLBACK_IN_PROGRESS" ]]; then
            log_warn "Stack ${stack} is in ${status} — wait for rollback to finish, then re-run cleanup."
        else
            log_ok "Stack ${stack} is in ${status} — no cleanup needed."
        fi
    done

    if ! $found_failed; then
        log_ok "No stacks in a failed state. Nothing to clean up."
    fi

    echo ""
    log_info "After cleanup, re-run: ./deploy.sh deploy"
}

# ── Commands ───────────────────────────────────────────────
cmd_bootstrap() {
    check_prerequisites
    install_deps
    source "${SCRIPT_DIR}/venv/bin/activate"
    update_cdk_config

    local account_id
    account_id=$(aws sts get-caller-identity --query Account --output text)
    log_info "Bootstrapping CDK for account ${account_id} in ${AWS_REGION}..."
    log_debug "Working directory: ${INFRA_DIR}"
    log_debug "Running: cdk bootstrap aws://${account_id}/${AWS_REGION} --verbose"
    cd "${INFRA_DIR}"

    # Run cdk bootstrap with --verbose so you can see exactly what's happening.
    # CDK bootstrap creates an S3 bucket + ECR repo + IAM roles in your account;
    # it can take 2-5 minutes on first run.
    if cdk bootstrap "aws://${account_id}/${AWS_REGION}" --verbose 2>&1 | tee /tmp/cdk_bootstrap.log; then
        log_ok "CDK bootstrap complete."
    else
        local exit_code=$?
        log_error "CDK bootstrap failed (exit code: ${exit_code})"
        log_error "Full log saved to: /tmp/cdk_bootstrap.log"
        log_error "Common fixes:"
        log_error "  - Check IAM permissions (AdministratorAccess or CDK-specific policy needed)"
        log_error "  - Verify region is correct: AWS_REGION=${AWS_REGION}"
        log_error "  - Check Docker is running (CDK bootstrap may build container assets)"
        log_error "  - Try: cdk bootstrap aws://${account_id}/${AWS_REGION} --verbose"
        exit ${exit_code}
    fi
}

cmd_synth() {
    install_deps
    source "${SCRIPT_DIR}/venv/bin/activate"
    update_cdk_config

    log_info "Synthesizing CloudFormation templates..."
    cd "${INFRA_DIR}"
    cdk synth --all
    log_ok "Synthesis complete. Templates in ${INFRA_DIR}/cdk.out/"
}

cmd_diff() {
    install_deps
    source "${SCRIPT_DIR}/venv/bin/activate"
    update_cdk_config

    log_info "Showing pending changes..."
    cd "${INFRA_DIR}"
    cdk diff --all
}

cmd_deploy() {
    check_prerequisites
    install_deps
    source "${SCRIPT_DIR}/venv/bin/activate"
    update_cdk_config

    log_info "Deploying all stacks to AWS (${AWS_REGION})..."
    echo ""
    log_warn "This will create/update AWS resources and may incur charges."
    read -rp "Continue? [y/N] " confirm
    if [[ ! "$confirm" =~ ^[yY]$ ]]; then
        log_info "Deployment cancelled."
        exit 0
    fi

    cd "${INFRA_DIR}"
    cdk deploy --all --require-approval broadening
    echo ""
    log_ok "Deployment complete!"
    cmd_status
}

cmd_deploy_stack() {
    local stack_name="$1"
    install_deps
    source "${SCRIPT_DIR}/venv/bin/activate"
    update_cdk_config

    log_info "Deploying stack: ${stack_name}..."
    cd "${INFRA_DIR}"
    cdk deploy "${stack_name}" --require-approval broadening
    log_ok "Stack ${stack_name} deployed."
}

cmd_destroy() {
    install_deps
    source "${SCRIPT_DIR}/venv/bin/activate"

    log_warn "⚠️  This will DESTROY all AWS resources for the Decoration Preview Service!"
    log_warn "S3 buckets with RETAIN policy will NOT be deleted."
    read -rp "Type 'destroy' to confirm: " confirm
    if [[ "$confirm" != "destroy" ]]; then
        log_info "Destruction cancelled."
        exit 0
    fi

    cd "${INFRA_DIR}"
    cdk destroy --all
    log_ok "Stacks destroyed."
}

cmd_status() {
    log_info "Stack outputs:"
    echo ""
    for stack in decoration-preview-network decoration-preview-storage decoration-preview-compute decoration-preview-api decoration-preview-monitoring; do
        echo -e "${BLUE}── ${stack} ──${NC}"
        aws cloudformation describe-stacks \
            --stack-name "${stack}" \
            --query 'Stacks[0].Outputs[*].[OutputKey,OutputValue]' \
            --output table \
            --region "${AWS_REGION}" 2>/dev/null || echo "  (not deployed)"
        echo ""
    done
}

# ── Main ───────────────────────────────────────────────────
case "${1:-help}" in
    bootstrap)
        cmd_bootstrap
        ;;
    synth)
        cmd_synth
        ;;
    diff)
        cmd_diff
        ;;
    deploy)
        cmd_deploy
        ;;
    deploy-stack)
        if [ -z "${2:-}" ]; then
            log_error "Usage: $0 deploy-stack <stack-name>"
            log_info "Available stacks:"
            echo "  decoration-preview-network"
            echo "  decoration-preview-storage"
            echo "  decoration-preview-compute"
            echo "  decoration-preview-api"
            echo "  decoration-preview-monitoring"
            exit 1
        fi
        cmd_deploy_stack "$2"
        ;;
    destroy)
        cmd_destroy
        ;;
    cleanup)
        cmd_cleanup
        ;;
    status)
        cmd_status
        ;;
    help|*)
        echo "Decoration Preview Service - AWS Deployment"
        echo ""
        echo "Usage: $0 <command>"
        echo ""
        echo "Commands:"
        echo "  bootstrap        Bootstrap CDK in your AWS account (first time)"
        echo "  synth            Synthesize CloudFormation templates (dry run)"
        echo "  diff             Show pending infrastructure changes"
        echo "  deploy           Deploy all stacks"
        echo "  deploy-stack <n> Deploy a specific stack"
        echo "  destroy          Destroy all stacks (CAUTION!)"
        echo "  cleanup          Delete failed stacks (ROLLBACK_COMPLETE)"
        echo "  status           Show deployment outputs"
        echo "  help             Show this help message"
        ;;
esac
