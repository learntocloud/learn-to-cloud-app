#!/bin/bash
#
# Ralph Loop - Iterative Python Library Review
# Based on Geoffrey Huntley's Ralph Wiggum technique
#
# Usage: ./ralph-loop.sh "path/to/file.py"
#
# Environment Variables:
#   RALPH_MAX_ITERATIONS - Max iterations before giving up (default: 5)
#   RALPH_WORKER_MODEL   - Model for worker agent (optional)
#   RALPH_REVIEWER_MODEL - Model for reviewer agent (optional)
#

set -e

# Configuration
MAX_ITERATIONS="${RALPH_MAX_ITERATIONS:-5}"
RALPH_DIR=".ralph"
FILE_TO_REVIEW="$1"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Helper functions
log_info() { echo -e "${BLUE}[INFO]${NC} $1"; }
log_success() { echo -e "${GREEN}[SUCCESS]${NC} $1"; }
log_warning() { echo -e "${YELLOW}[WARNING]${NC} $1"; }
log_error() { echo -e "${RED}[ERROR]${NC} $1"; }

# Validate input
if [ -z "$FILE_TO_REVIEW" ]; then
    log_error "Usage: $0 <path/to/file.py>"
    exit 1
fi

if [ ! -f "$FILE_TO_REVIEW" ]; then
    log_error "File not found: $FILE_TO_REVIEW"
    exit 1
fi

# Check for copilot CLI
if ! command -v copilot &> /dev/null; then
    log_error "GitHub Copilot CLI not found. Install it first."
    log_info "See: https://docs.github.com/en/copilot/how-tos/use-copilot-agents/use-copilot-cli"
    exit 1
fi

# Initialize Ralph directory
mkdir -p "$RALPH_DIR"

log_info "Starting Ralph Loop for: $FILE_TO_REVIEW"
log_info "Max iterations: $MAX_ITERATIONS"

# Initialize state file
cat > "$RALPH_DIR/state.md" << EOF
## Current State
- Iteration: 1
- Status: not_started
- File to review: $FILE_TO_REVIEW
- Libraries researched: 0
- Issues found: 0
- Fixes proposed: 0
EOF

# Clear any prior output/feedback
rm -f "$RALPH_DIR/output.md" "$RALPH_DIR/feedback.md"

iteration=1
status="not_started"

while [ $iteration -le $MAX_ITERATIONS ]; do
    echo ""
    log_info "=========================================="
    log_info "ITERATION $iteration of $MAX_ITERATIONS"
    log_info "=========================================="
    
    # WORKER PHASE
    echo ""
    log_info "🔧 Running Worker Agent..."
    
    worker_prompt="Perform a deep-dive Python library review of the file specified in .ralph/state.md. 
Read any prior feedback in .ralph/feedback.md and address all concerns.
Follow ALL phases from your instructions. Fetch real documentation and cite sources.
Write your complete output to .ralph/output.md and update .ralph/state.md when done."

    # Run worker agent
    if copilot --agent=ralph-worker --prompt "$worker_prompt"; then
        log_success "Worker completed"
    else
        log_error "Worker failed"
        exit 1
    fi
    
    # Check if output was created
    if [ ! -f "$RALPH_DIR/output.md" ]; then
        log_error "Worker did not create output file"
        exit 1
    fi
    
    # REVIEWER PHASE
    echo ""
    log_info "🔍 Running Reviewer Agent..."
    
    reviewer_prompt="Review the worker's Python library review in .ralph/output.md.
Check completeness, citations, accuracy. Spot-check 1-2 claims.
Either APPROVE (write status: approved to state.md) or REJECT (write specific feedback to feedback.md).
Be specific about what's missing or wrong."

    # Run reviewer agent
    if copilot --agent=ralph-reviewer --prompt "$reviewer_prompt"; then
        log_success "Reviewer completed"
    else
        log_error "Reviewer failed"
        exit 1
    fi
    
    # Check status
    status=$(grep -E "^- Status:" "$RALPH_DIR/state.md" | sed 's/.*: //' || echo "unknown")
    
    if [ "$status" = "approved" ]; then
        echo ""
        log_success "=========================================="
        log_success "🚀 APPROVED after $iteration iteration(s)!"
        log_success "=========================================="
        log_info "Review output: $RALPH_DIR/output.md"
        exit 0
    elif [ "$status" = "needs_work" ]; then
        log_warning "Reviewer requested changes. Continuing loop..."
        
        # Update iteration in state file
        ((iteration++))
        sed -i '' "s/Iteration: [0-9]*/Iteration: $iteration/" "$RALPH_DIR/state.md" 2>/dev/null || \
        sed -i "s/Iteration: [0-9]*/Iteration: $iteration/" "$RALPH_DIR/state.md"
    else
        log_error "Unexpected status: $status"
        exit 1
    fi
done

echo ""
log_error "=========================================="
log_error "❌ MAX ITERATIONS ($MAX_ITERATIONS) REACHED"
log_error "=========================================="
log_info "Review the current state in $RALPH_DIR/"
log_info "You can increase RALPH_MAX_ITERATIONS and continue"
exit 1
