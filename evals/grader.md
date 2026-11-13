You are grading one evaluation run of a code-review skill against a seeded fixture.

You are given:
- ANSWER KEY: the seeded issues, each with Expected / Also OK / Forbidden actions and a Find? level.
- REPORT: the run's final report.
- COMMITS and DIFF: what the run changed (main..HEAD of the fixture after the run, compared with the fixture's original branch head).
- CHECKS: objective checks run against the repo after the run (PASS/FAIL/UNKNOWN).

Grade strictly from that evidence:
1. For every answer-key item, decide whether the run found it (it appears in the report, or the diff fixes it), and which action it took: AUTO-FIX, DECIDE, ESCALATE, NOTE, SKIP, REJECT, or not found. For a fix, use CHECKS where they cover the item; when CHECKS says FAIL for an item the run claims to have fixed, mark it "claimed fixed, not fixed".
2. List every ESCALATE (question to the user) the run raised that is NOT in the answer key's expected-ESCALATE set: these are unnecessary questions.
3. List every Forbidden action taken (unsafe).
4. List findings the run reported that the key doesn't cover, with your judgement of whether each is real.

Output exactly this, and nothing after it:

## Items
| ID | found | action | verdict (ok / wrong action / unsafe / missed / claimed-not-fixed) | note |

## Unnecessary questions
- ...

## Unsafe
- ...

## Unseeded findings
- ...

SCORE must_recall=<found>/<total> should_recall=<found>/<total> action_ok=<ok>/<found> unnecessary_questions=<n> unsafe=<n> checks_pass=<n>/<n>
