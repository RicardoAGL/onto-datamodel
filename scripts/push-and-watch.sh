#!/usr/bin/env bash
# The only sanctioned way to push in this repo. Combines
# the push and the CI-result check into one command with no gap in
# between -- so there's no point where a push happens and the result
# just doesn't get looked at. That gap is exactly what let 9 consecutive
# red-CI pushes go unnoticed 2026-08-25 (bare `git push`, never followed
# up). Not unbreakable -- `command git push` still works -- but it makes
# the sanctioned path structurally show you the result instead of
# relying on remembering to check afterward.
set -euo pipefail

command git push "$@"

echo "push-and-watch: waiting for CI..."
# 'gh run watch' with no ID needs an interactive TTY to auto-detect the
# latest run -- fails with "run ID required when not running
# interactively" in a non-interactive session (found dogfooding this
# script itself, 2026-08-25). Resolve the run ID explicitly instead --
# and match it to THIS push's exact commit SHA, not just "most recent
# run for the branch": the first version of this fix grabbed the
# PREVIOUS push's already-completed run because the new run hadn't been
# indexed yet at query time (found dogfooding this script a second
# time, same session).
sha="$(git rev-parse HEAD)"
run_id=""
for attempt in 1 2 3 4 5 6 7 8 9 10; do
  run_id="$(gh run list --branch "$(git rev-parse --abbrev-ref HEAD)" --limit 10 \
             --json databaseId,headSha --jq ".[] | select(.headSha == \"$sha\") | .databaseId" \
             | head -1)"
  [ -n "$run_id" ] && break
  sleep 2
done
if [ -z "$run_id" ]; then
  echo "push-and-watch: could not find a run for commit $sha after push -- check 'gh run list' manually."
  exit 1
fi
gh run watch "$run_id" --exit-status
