#!/usr/bin/env bash
# GitHub issue -> factory run in a worktree -> commit, push, PR that closes it.
#
#   scripts/issue-to-pr.sh 1 [extra factory args, e.g. --attempts=2]
#
# Needs: factory, gh (authenticated), uv, bun. Publishing happens only after
# factory passes, so retries never create duplicate commits or PRs.
set -euo pipefail

issue="${1:?usage: scripts/issue-to-pr.sh <issue-number> [factory args...]}"
shift
cd "$(git rev-parse --show-toplevel)"

title=$(gh issue view "$issue" --json title --jq .title)
task="GitHub issue #$issue
$(gh issue view "$issue" --comments)"

out=$(mktemp)
set +e
factory "$task" --stage=issue --attempts=3 --timeout=900 "$@" | tee "$out"
status=${PIPESTATUS[0]}
set -e
run_dir=$(sed -n 's/^Run: //p' "$out" | head -1)
workspace=$(sed -n 's/^Workspace: //p' "$out" | head -1)
rm -f "$out"

if [ "$status" -ne 0 ]; then
  echo "Factory needs attention (exit $status)." >&2
  echo "  Logs:     $run_dir" >&2
  echo "  Worktree: $workspace" >&2
  exit "$status"
fi

branch="factory/$(basename "$run_dir")"
summary="$(ls -d "$run_dir"/attempt-* | tail -1)/summary.md"

git -C "$workspace" add -A
if git -C "$workspace" diff --cached --quiet; then
  echo "Factory passed but changed nothing; no PR opened. Worktree: $workspace" >&2
  exit 1
fi
git -C "$workspace" commit -q -m "$title" -m "Closes #$issue"
git -C "$workspace" push -u origin "$branch"

body=$(mktemp)
{ cat "$summary"; printf '\nCloses #%s\n\n_Built by factory run %s._\n' "$issue" "$(basename "$run_dir")"; } > "$body"
gh pr create --head "$branch" --title "$title" --body-file "$body"
rm -f "$body"

echo "Done. After the PR merges: git worktree remove \"$workspace\" && git branch -D \"$branch\""
