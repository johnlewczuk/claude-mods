# Review-skills ledger

`review-until-clean` and `prepare-pr` log every triaged item and every answer the user gives, so `review-retro` can learn from what happened.

**Path:** `${CLAUDE_SKILL_LEDGER:-$HOME/.claude/skill-ledgers/review-skills.jsonl}`
- The file is append-only, one JSON object per line. Never edit or delete an existing line.
- Create the directory if it is missing.
- It is local and private. It must never go into a repo.

## Item lines

Write these when the report is written, one line per item:

```json
{"type": "item", "ts": "<ISO time>", "skill": "review-until-clean|prepare-pr",
 "run": "<repo dir name>:<branch>@<start sha, 7>", "repo": "<absolute repo path>",
 "item": "F2.3|H1|R3|X1|HY2|S", "source": "review|holistic|spec|hygiene|simplify",
 "category": "<slug from the list below>", "action": "AUTO-FIX|DECIDE|ESCALATE|NOTE|SKIP|REJECT",
 "summary": "<one line>", "recommendation": "<for ESCALATE: the option you recommended; for DECIDE: the option you chose>",
 "alternatives": "<for ESCALATE/DECIDE: the other options>", "commit": "<sha or null>"}
```

When `review-until-clean` runs inside `prepare-pr`, both skills use the same `run` value.

## Outcome lines

Append one line for each user answer **before acting on it**:

```json
{"type": "outcome", "ts": "<ISO time>", "run": "<same run>", "item": "<same item>",
 "outcome": "accepted-recommendation|chose-other: <which>|reverted|kept|missed",
 "detail": "<the user's words, one line>"}
```

What each outcome means:
- `accepted-recommendation`: the user picked exactly the option you recommended. This is the signal that the question wasn't needed.
- `chose-other`: the user picked a different option. Say which.
- `reverted`: the user undid an AUTO-FIX or DECIDE commit.
- `missed`: the user, a PR reviewer or a later fix found something the run should have reported. Use `item` `M<n>` and set `category`.

## Category slugs

| Group | Slugs |
|---|---|
| Correctness | `null-handling`, `error-handling`, `resource-leak`, `injection`, `atomicity`, `time`, `boundary`, `state-consistency`, `concurrency`, `validation` |
| Design | `duplication`, `reuse`, `layering`, `dead-code`, `speculative`, `control-flow`, `redundant-state`, `config` |
| Decisions | `contract`, `scope`, `intent`, `behavior-change` |
| Hygiene | `debug-leftover`, `scratch-file`, `planning-doc`, `secret`, `housekeeping` |
| Spec | `spec-missing`, `spec-partial`, `spec-deferred` |
| Anything else | `other`, plus a short note in `summary` |
