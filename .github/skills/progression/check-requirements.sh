#!/bin/bash
# Validate that PHASE_REQUIREMENTS in code matches actual content files
# Run from repo root: ./.github/skills/progression/check-requirements.sh

set -e

REPO_ROOT="$(cd "$(dirname "$0")/../../.." && pwd)"
cd "$REPO_ROOT"

echo "🔍 Checking phase requirements vs content..."
echo ""

# Count steps and questions from content files
echo "📄 Content files (content/phases/):"
echo "----------------------------------------"
for phase in 0 1 2 3 4 5 6; do
    phase_dir="content/phases/phase${phase}"
    if [[ -d "$phase_dir" ]]; then
        total_steps=0
        total_questions=0
        for f in "$phase_dir"/*.json; do
            [[ "$(basename "$f")" == "index.json" ]] && continue
            [[ ! -f "$f" ]] && continue
            steps=$(jq '.learning_steps | length' "$f" 2>/dev/null || echo 0)
            questions=$(jq '.questions | length' "$f" 2>/dev/null || echo 0)
            total_steps=$((total_steps + steps))
            total_questions=$((total_questions + questions))
        done
        echo "Phase $phase: $total_steps steps, $total_questions questions"
    fi
done

echo ""
echo "🐍 Code requirements (api/services/progress.py):"
echo "----------------------------------------"
cd api
.venv/bin/python -c "
from services.progress import PHASE_REQUIREMENTS
for phase_id in sorted(PHASE_REQUIREMENTS.keys()):
    req = PHASE_REQUIREMENTS[phase_id]
    print(f'Phase {phase_id}: {req[\"total_steps\"]} steps, {req[\"total_questions\"]} questions')
"

echo ""
echo "🔧 Hands-on requirements (api/services/hands_on_verification.py):"
echo "----------------------------------------"
.venv/bin/python -c "
from services.hands_on_verification import HANDS_ON_REQUIREMENTS
for phase_id in sorted(HANDS_ON_REQUIREMENTS.keys()):
    print(f'Phase {phase_id}: {len(HANDS_ON_REQUIREMENTS[phase_id])} hands-on requirements')
"

echo ""
echo "✅ Review above to ensure content matches code requirements!"
