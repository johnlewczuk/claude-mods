#!/usr/bin/env bash
# Cheap eval: one fresh session triages a fixed findings set with review-until-clean's
# table; graded mechanically against expected.txt. ~1 minute, a few cents per rep.
# Usage: run-triage.sh <case> [reps]     e.g. run-triage.sh device-ingest 3
set -euo pipefail
here=$(cd "$(dirname "$0")" && pwd)
case_dir=$here/triage/$1; reps=${2:-3}
skill=$here/../skills/review-until-clean/SKILL.md
out=$(mktemp -d "${TMPDIR:-/tmp}/triage-$1-XXXX")
pass_all=0; total_all=0
for r in $(seq 1 "$reps"); do
  claude -p --no-session-persistence --permission-mode bypassPermissions --max-budget-usd 2 \
    "Read the skill $skill and the round-1 findings $case_dir/findings.md. Act as the orchestrator at step '2. Triage' of round 1: write the triage record for every finding and set its action by the skill's table. The repo is not available; take the findings' facts as true. Change no files. For each AUTO-FIX, state the exact fix (commands included). End your reply with one line per finding, exactly: RESULT <id> <ACTION>" \
    > "$out/rep$r.txt" 2>&1 || true
  while read -r id rest; do
    [[ $id == \#* || -z $id ]] && continue
    acts=${rest%%~*}; method=""; [[ $rest == *"~"* ]] && method=${rest#*~}
    got=$(grep -E "^RESULT $id " "$out/rep$r.txt" | tail -1 | awk '{print $3}')
    total_all=$((total_all+1))
    if [[ " $acts " != *" $got "* ]]; then echo "rep$r $id: got '${got:-none}', want one of: $acts"
    elif [[ -n $method ]] && ! grep -qE -- "$method" "$out/rep$r.txt"; then echo "rep$r $id: action ok but transcript lacks '$method'"
    else pass_all=$((pass_all+1)); fi
  done < "$case_dir/expected.txt"
done
echo "triage $1: $pass_all/$total_all correct over $reps reps  (transcripts: $out)"
