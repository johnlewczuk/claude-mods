# Skill evals

Regression suite for `skills/review-until-clean` and `skills/prepare-pr`. Every change to
either skill (by hand or from a retro) must keep these passing; every real failure a
retro finds becomes a new case here.

## Cases

| Case | Kind | Cost | What it tests |
|---|---|---|---|
| `triage/device-ingest` | triage only | cents, ~1 min/rep | review-until-clean's triage table on 8 fixed findings |
| `fixtures/alerts` | full run | a few $ | prepare-pr: spec gaps, speculative/out-of-scope code, hygiene |
| `fixtures/fleetd` | full run | $10–30 | both skills: ~11 bugs, 5 architecture, 8 simplification/reuse, 8 traps, spec + hygiene |

Fixtures are source trees (`base/`, `branch/<n>-<step>/`, messages), built into a fresh
git repo by `build-fixture.sh` so they never nest a repo inside this one. Each has an
`answer-key.md` (graders only — never give it to a run) and optionally `checks.py`, which
checks a run's fixes by executing the code.

## Running

    ./run-triage.sh device-ingest 3          # cheap, mechanical grading
    ./run-eval.sh prepare-pr alerts 10       # full run + grader; budget cap in USD
    ./run-eval.sh review-until-clean fleetd 30
    ./run-eval.sh prepare-pr fleetd 30

A full run executes the skill in a fresh `claude -p` session (bypassPermissions, inside
the throwaway fixture repo, with the user's normal global setup), then `checks.py`, then a
grader session with the answer key. Its ledger goes to the run dir, not the real ledger
(`CLAUDE_SKILL_LEDGER`). One scorecard row is appended to `results.md`:

- `must_recall`, `should_recall` — seeded items found
- `action_ok` — found items with an acceptable action
- `unnecessary_questions` — escalations outside the expected set (the "too conservative" metric)
- `unsafe` — forbidden actions; must be 0
- `checks_pass` — objective fix checks

Model output varies: compare skill versions on 2+ runs each, never on one.

## Adding a case

From a retro: reproduce the real failure as the smallest fixture that shows it
(anonymized — no real project, customer, or person names; this repo is public), add its
rows to an answer key with Expected / Also OK / Forbidden, and confirm the current skill
fails it before changing the skill.
