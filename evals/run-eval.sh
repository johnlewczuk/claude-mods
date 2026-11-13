#!/usr/bin/env bash
# Full eval: build a fixture, run a skill on it in a fresh headless session, run the
# fixture's objective checks, grade the run against the answer key, append a scorecard.
# Usage: run-eval.sh <skill> <fixture> [budget-usd]
#   skill:   review-until-clean | prepare-pr
#   fixture: fleetd | alerts
# Costs real money: a prepare-pr run on fleetd is a full review-fix loop.
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
skill=$1; fixture=$2; budget=${3:-25}
fx=$here/fixtures/$fixture
stamp=$(date +%Y%m%d-%H%M%S)
out=${EVAL_OUT:-${TMPDIR:-/tmp}/skill-evals}/$skill-$fixture-$stamp
mkdir -p "$out"
repo=$out/repo
"$here/build-fixture.sh" "$fixture" "$repo" >/dev/null
start=$(git -C "$repo" rev-parse HEAD)
spec=$(cd "$repo" && ls docs/specs/*.md 2>/dev/null | head -1 || true)

case $skill in
  review-until-clean) cmd="/review-until-clean high --rounds 3 --test \"python3 -m pytest -q\"" ;;
  prepare-pr)         cmd="/prepare-pr --spec ${spec:-none}" ;;
  *) echo "unknown skill: $skill" >&2; exit 1 ;;
esac

note="This is a non-interactive evaluation run: nobody can answer questions mid-run. Where a skill says to ask the user during setup (which spec, which commands), proceed with your best assumption and state it in the report. Escalations still go in the report as usual and must not be acted on. There is no git remote; skip pushing and issue searches."
echo "running: $cmd  (out: $out)"
( cd "$repo" && CLAUDE_SKILL_LEDGER="$out/ledger.jsonl" claude -p "$cmd" \
    --append-system-prompt "$note" --permission-mode bypassPermissions \
    --max-budget-usd "$budget" --output-format text ) > "$out/report.md" 2> "$out/stderr.txt" || true

git -C "$repo" log --oneline "$start..HEAD" > "$out/commits.txt" || true
git -C "$repo" diff "$start" > "$out/diff.patch" || true
if [[ -f $fx/checks.py ]]; then python3 -I "$fx/checks.py" "$repo" > "$out/checks.txt" 2>&1 || true; fi

{
  echo "# ANSWER KEY"; cat "$fx/answer-key.md"
  echo; echo "# REPORT"; cat "$out/report.md"
  echo; echo "# COMMITS"; cat "$out/commits.txt"
  echo; echo "# DIFF"; head -c 200000 "$out/diff.patch"
  echo; echo "# CHECKS"; cat "$out/checks.txt" 2>/dev/null || echo "(none)"
} > "$out/grader-input.md"
claude -p --no-session-persistence --max-budget-usd 3 --permission-mode bypassPermissions \
  "$(cat "$here/grader.md")

The material to grade is in $out/grader-input.md. Read it in full." > "$out/score.md" 2>&1 || true

score=$(grep -E '^SCORE ' "$out/score.md" | tail -1 || echo "SCORE (grader failed)")
skill_rev=$(git -C "$here/.." log -1 --format=%h -- "skills/$skill" 2>/dev/null || echo uncommitted)
dirty=$(git -C "$here/.." status --porcelain -- "skills/$skill" | head -1)
echo "| $(date +%F) | $skill @ $skill_rev${dirty:+ (dirty)} | $fixture | ${score#SCORE } | $out |" >> "$here/results.md"
echo "$score"; echo "details: $out"
