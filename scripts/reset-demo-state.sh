#!/usr/bin/env bash
# Resets the repo back to the demo's real starting state after a
# rehearsal (or after the actual talk). Safe to run repeatedly.
#
# What a rehearsal run of the live demo can leave behind:
#   1. scripts/generate_remaining_entities.py -- the stg_kiosk_sales entity gets
#      added here during the live grounding exercise.
#   2. models/staging/_staging_models.yml -- order_total's description
#      gets corrected here too, scripts/validate_grounding.py requires both to
#      agree (see AGENTS.md / the security review that added this rule).
#   3. review_signoffs.json -- untracked but NOT gitignored, deliberately
#      (see ADR-002, a signed commit of this file IS the human signature),
#      only appears if `sign` was actually run.
#   4. questionnaires/ -- gitignored, only appears if the questionnaire
#      generator was run and rendered.
#   5. target/, structural_facts.json, ontology.ttl, ontology_report.html
#      -- all gitignored, all fully regeneratable from the tracked
#      source files above. Rebuilt fresh, never hand-edited back.
#
# What this script deliberately does NOT touch: anything outside that
# list. If a rehearsal (or anything else) left other tracked files
# modified, this script stops and shows them rather than guessing.
set -euo pipefail

cd "$(dirname "$0")/.."

DEMO_TRACKED_FILES=(
  "scripts/generate_remaining_entities.py"
  "models/staging/_staging_models.yml"
)
# review_signoffs.json is untracked-but-not-gitignored (deliberate,
# ADR-002) -- it's a KNOWN rehearsal leftover this script cleans up
# below, so it must not trip the "unexpected changes" check either.
KNOWN_UNTRACKED_FILES=(
  "review_signoffs.json"
)

echo "reset-demo-state: checking for changes outside the known demo touch points..."
unexpected=$(command git status --short -- . \
  ":(exclude)${DEMO_TRACKED_FILES[0]}" \
  ":(exclude)${DEMO_TRACKED_FILES[1]}" \
  ":(exclude)${KNOWN_UNTRACKED_FILES[0]}")
if [ -n "$unexpected" ]; then
  echo "reset-demo-state: found unrelated uncommitted changes, stopping without touching them:"
  echo "$unexpected"
  echo "reset-demo-state: handle those first (commit, stash, or discard by hand), then re-run."
  exit 1
fi

echo "reset-demo-state: restoring the two known demo files..."
command git restore "${DEMO_TRACKED_FILES[@]}" 2>/dev/null || true

echo "reset-demo-state: clearing rehearsal-only untracked state (signoffs, rendered questionnaires)..."
rm -f review_signoffs.json
rm -rf questionnaires/

echo "reset-demo-state: rebuilding dbt so the manifest matches the restored schema.yml..."
uv run dbt build > /dev/null

echo "reset-demo-state: re-extracting structural facts..."
python3 scripts/extract_structural_facts.py

echo "reset-demo-state: verifying the real starting state (expect: 1 coverage gap, stg_kiosk_sales)..."
python3 scripts/validate_coverage.py

echo "reset-demo-state: done. Repo is back to the pre-demo starting state."
