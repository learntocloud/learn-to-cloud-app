#!/bin/bash
# =============================================================================
# Debug Deploy Workflow Script
# =============================================================================
# This script helps diagnose and fix issues with the GitHub Actions deploy workflow.
# Usage: ./scripts/debug-deploy.sh [command]
#
# Commands:
#   status    - Show recent workflow runs and their status (default)
#   logs      - View failed logs from the most recent run
#   logs <id> - View failed logs from a specific run
#   unlock    - Force unlock Terraform state if locked
#   rerun     - Re-run the most recent failed workflow
#   rerun <id>- Re-run a specific workflow
#   watch     - Watch the most recent workflow run in real-time
# =============================================================================

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Navigate to repo root
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$REPO_ROOT"

print_header() {
    echo -e "\n${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
    echo -e "${BLUE}  $1${NC}"
    echo -e "${BLUE}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}\n"
}

print_success() {
    echo -e "${GREEN}✓ $1${NC}"
}

print_error() {
    echo -e "${RED}✗ $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}⚠ $1${NC}"
}

print_info() {
    echo -e "${BLUE}ℹ $1${NC}"
}

# Get the most recent workflow run ID
get_latest_run_id() {
    gh run list --workflow=deploy.yml --limit 1 --json databaseId --jq '.[0].databaseId'
}

# Get the most recent failed workflow run ID
get_latest_failed_run_id() {
    gh run list --workflow=deploy.yml --status=failure --limit 1 --json databaseId --jq '.[0].databaseId'
}

# Show recent workflow runs
cmd_status() {
    print_header "Recent Deploy Workflow Runs"
    gh run list --workflow=deploy.yml --limit 10

    echo ""
    print_info "Use './scripts/debug-deploy.sh logs <run-id>' to view logs for a specific run"
}

# View failed logs
cmd_logs() {
    local run_id="${1:-$(get_latest_failed_run_id)}"

    if [ -z "$run_id" ]; then
        print_error "No failed workflow runs found"
        exit 1
    fi

    print_header "Failed Logs for Run #$run_id"

    # Get run info first
    echo -e "${YELLOW}Run Details:${NC}"
    gh run view "$run_id"

    echo ""
    print_header "Failed Step Logs"
    gh run view "$run_id" --log-failed

    # Check for common issues
    echo ""
    print_header "Automated Issue Detection"

    local logs=$(gh run view "$run_id" --log-failed 2>&1)

    # Check for Terraform state lock
    if echo "$logs" | grep -q "Error acquiring the state lock\|state blob is already locked"; then
        print_error "DETECTED: Terraform State Lock Issue"
        echo ""
        echo "The Terraform state file is locked by another process."
        echo ""
        echo "To fix this, run:"
        echo -e "  ${GREEN}./scripts/debug-deploy.sh unlock${NC}"
        echo ""

        # Extract lock ID if present
        local lock_id=$(echo "$logs" | grep -oP 'ID:\s+\K[a-f0-9-]+' | head -1)
        if [ -n "$lock_id" ]; then
            print_info "Lock ID: $lock_id"
        fi
    fi

    # Check for authentication issues
    if echo "$logs" | grep -q "AuthorizationFailed\|AADSTS\|authentication\|unauthorized"; then
        print_error "DETECTED: Authentication/Authorization Issue"
        echo ""
        echo "Check that AZURE_CREDENTIALS secret is valid and not expired."
        echo "The service principal may need its credentials rotated."
    fi

    # Check for resource not found
    if echo "$logs" | grep -q "ResourceNotFound\|does not exist"; then
        print_error "DETECTED: Resource Not Found"
        echo ""
        echo "An Azure resource referenced in Terraform may have been deleted outside of Terraform."
        echo "Consider running 'terraform refresh' or updating the state."
    fi

    # Check for quota issues
    if echo "$logs" | grep -q "QuotaExceeded\|exceeds the quota"; then
        print_error "DETECTED: Azure Quota Exceeded"
        echo ""
        echo "You've hit an Azure subscription quota limit."
        echo "Request a quota increase in the Azure portal or clean up unused resources."
    fi

    # Check for test failures
    if echo "$logs" | grep -q "FAILED\|pytest\|AssertionError"; then
        print_warning "DETECTED: Test Failures"
        echo ""
        echo "One or more tests failed. Review the test output above."
    fi

    # Check for lint failures
    if echo "$logs" | grep -q "ruff\|lint error\|E501\|F401"; then
        print_warning "DETECTED: Linting Issues"
        echo ""
        echo "Code linting failed. Run 'ruff check api/' locally to see issues."
    fi
}

# Force unlock Terraform state
cmd_unlock() {
    print_header "Terraform State Unlock"

    cd "$REPO_ROOT/infra"

    # Initialize terraform if needed
    if [ ! -d ".terraform" ]; then
        print_info "Initializing Terraform..."
        terraform init
    fi

    # Try to get the current lock info
    print_info "Checking for state lock..."

    # Attempt a plan to see if there's a lock
    local plan_output=$(terraform plan -lock-timeout=5s 2>&1 || true)

    if echo "$plan_output" | grep -q "Error acquiring the state lock"; then
        local lock_id=$(echo "$plan_output" | grep -oP 'ID:\s+\K[a-f0-9-]+' | head -1)

        if [ -n "$lock_id" ]; then
            print_warning "Found lock ID: $lock_id"
            echo ""
            read -p "Force unlock this state? (y/N) " -n 1 -r
            echo ""

            if [[ $REPLY =~ ^[Yy]$ ]]; then
                terraform force-unlock -force "$lock_id"
                print_success "State unlocked successfully!"
            else
                print_info "Unlock cancelled"
            fi
        else
            print_error "Could not extract lock ID from error message"
            echo "You may need to manually unlock via Azure Portal or az CLI"
        fi
    else
        print_success "No state lock detected - state is available"
    fi
}

# Re-run a workflow
cmd_rerun() {
    local run_id="${1:-$(get_latest_failed_run_id)}"

    if [ -z "$run_id" ]; then
        print_error "No workflow run found to re-run"
        exit 1
    fi

    print_header "Re-running Workflow #$run_id"

    gh run rerun "$run_id"
    print_success "Workflow re-run requested!"

    echo ""
    print_info "Watch the run with: ./scripts/debug-deploy.sh watch"
}

# Watch a workflow run
cmd_watch() {
    local run_id="${1:-$(get_latest_run_id)}"

    if [ -z "$run_id" ]; then
        print_error "No workflow run found"
        exit 1
    fi

    print_header "Watching Workflow #$run_id"
    gh run watch "$run_id"
}

# Show help
cmd_help() {
    cat << EOF
Debug Deploy Workflow Script

Usage: ./scripts/debug-deploy.sh [command] [args]

Commands:
  status          Show recent workflow runs and their status (default)
  logs [run-id]   View failed logs (defaults to most recent failed run)
  unlock          Force unlock Terraform state if locked
  rerun [run-id]  Re-run a workflow (defaults to most recent failed run)
  watch [run-id]  Watch a workflow run in real-time
  help            Show this help message

Examples:
  ./scripts/debug-deploy.sh                    # Show status
  ./scripts/debug-deploy.sh logs               # View most recent failure
  ./scripts/debug-deploy.sh logs 12345678      # View specific run
  ./scripts/debug-deploy.sh unlock             # Fix Terraform lock
  ./scripts/debug-deploy.sh rerun              # Re-run latest failed

Common Issues Detected:
  • Terraform State Lock - Run 'unlock' command to fix
  • Authentication Errors - Check AZURE_CREDENTIALS secret
  • Resource Not Found - Resource may have been deleted outside Terraform
  • Quota Exceeded - Request quota increase or clean up resources
  • Test Failures - Run tests locally with 'pytest api/tests/'
  • Lint Failures - Run 'ruff check api/' locally

EOF
}

# Main command router
case "${1:-status}" in
    status)
        cmd_status
        ;;
    logs)
        cmd_logs "$2"
        ;;
    unlock)
        cmd_unlock
        ;;
    rerun)
        cmd_rerun "$2"
        ;;
    watch)
        cmd_watch "$2"
        ;;
    help|--help|-h)
        cmd_help
        ;;
    *)
        print_error "Unknown command: $1"
        cmd_help
        exit 1
        ;;
esac
