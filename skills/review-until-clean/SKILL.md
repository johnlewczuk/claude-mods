---
name: review-until-clean
description: Use when the user wants a branch reviewed and fixed repeatedly until no problems remain — a review-fix loop, "keep running /code-review until it's clean", or iterative pre-merge cleanup of the current branch.
argument-hint: "[low|medium|high|xhigh|max] [--pr N | <from>..<to> | --base REF] [--rounds N] [--report-only] [--test CMD]"
---

# Review Until Clean

## Overview

Loop: fresh-context review → triage → fix → test → commit. Stop on convergence, a cap, red tests, or oscillation, then do one holistic design pass and apply what it finds.

**Core principle:** fix everything the code can settle; ask the user only about what it can't. The size or shape of a fix is never a reason to ask: a root-cause fix upstream, consolidating duplicated logic, a new helper, or an internal signature change is a decision the code settles. Ask only when the correct behavior depends on intent that the spec, code, tests, docs and domain don't settle, or when the fix changes an external contract. Every fix is its own commit, so a decision the user disagrees with costs one `git revert`; the report lists every judgment call, so the user audits afterwards instead of approving beforehand.

## Setup

1. Parse args. Defaults: level `high`, `--rounds 3`, fixes enabled.
2. The session's working directory must be inside the target repo: `code-review` always reviews the session directory (a `cd` in Bash does not change that). If it isn't, refuse and tell the user to start Claude Code in the repo.
3. Refuse to start with uncommitted changes to tracked files; tell the user why. Untracked build output (`__pycache__/`, `build/`) is fine.
4. Resolve the target to a base. Use the first form given (at most one is allowed):

   | Form | Checkout | Base | Mode |
   |---|---|---|---|
   | `--pr N` | `gh pr checkout N` (note the branch you were on, for the report) | `gh pr view N --json baseRefName`, then `git fetch origin <baseRefName>` → `origin/<baseRefName>` | as requested |
   | `<from>..<to>` where `<to>` resolves to the same SHA as `HEAD` | unchanged | `<from>` | as requested |
   | `<from>..<to>` otherwise | `git worktree add --detach .claude/worktrees/rvc-<short-sha> <to>` from the repo root, then `EnterWorktree` with that `path` (the user asked for this range, which authorizes it) | `<from>` | **report-only** (fixes can't land mid-history); say so in the report |
   | `--base REF` | unchanged | `REF` | as requested |
   | none | unchanged | merge-base with the default branch | as requested |

   If fixes are enabled and the checkout is the default branch, refuse (offer `--report-only`). For a worktree: at the end, `ExitWorktree` with `action: "keep"`, and give the user its `git worktree remove` command in the report.
5. Fixes are local commits only — never push, including for `--pr`. The report tells the user to push if they want the fixes on the PR.
6. Determine the test command: `--test`, else CLAUDE.md / project docs, else ask the user once. Projects with special build rules (e.g. remote build hosts in CLAUDE.md) use those rules.
7. Record the starting SHA so the user can `git reset` to it.

## Each round (k = 1..rounds)

### 1. Review — fresh subagent every round

Dispatch a **new** general-purpose subagent. Do not invoke `code-review` yourself: it runs as a fork of its caller, so it would inherit your context and your reasoning about the fixes. The subagent's prompt contains only the base ref and level, and asks it to:
1. invoke the `code-review` skill with exactly `<level> <base>..HEAD --max-findings all`. Always the `..HEAD` range: a bare SHA makes `code-review` review *that commit*, not the branch. Always pass the level and `--max-findings` explicitly, because omitted ones reuse whatever the user last typed. Never `--fix`, `--comment` or `--post`;
2. check the scope of the review as a whole: if `code-review` prints a scope statement naming a range other than `<base>..HEAD`, or no finding's file appears in `git diff --name-only <base>...HEAD`, return `SCOPE MISMATCH` with the evidence instead of findings. A finding in a file outside that list is otherwise legitimate (a caller the branch breaks, the upstream source of a bug, nearby debt): mark it `out-of-diff` and keep it;
3. for each finding, read the callers, callees and similar code, then label its `failure_scenario`:
   - `verified-by-running` — it ran the code with an input that real callers or config can actually produce;
   - `verified-by-reading` — it traced a path from real callers/config to the failure;
   - `assumption` — the triggering input is outside what callers (including tests), config, or the code's evident contract (types, docstrings, the domain — e.g. any valid port) can produce, even if a made-up input reproduces it;
   - `refuted` — with the refuting line or run;
4. keep any scratch files it creates in the session scratchpad, never the repo;
5. return each finding as `file:line — summary — category — failure_scenario — evidence label [— out-of-diff]`.

If `code-review` is unavailable or errors, or the subagent reports `SCOPE MISMATCH`, stop the loop and report it. Never substitute a hand-written review — the loop's results must come from the same reviewer every round.

Give it no history of previous rounds — it must read the code cold. `code-review` reports cleanups (reuse, simplification, efficiency) as well as bugs; triage decides what each one becomes.

### 2. Triage — one record per finding (REQUIRED)

Before touching code, write this record for **every** finding. If parts of one finding would get different actions (e.g. a bug whose fix also changes a config key), split it into separate records first; a part that duplicates another finding from the same round becomes `F<k>.<n> = F<k>.<m> (folded)`. A finding that repeats one (or part of one) already ESCALATED, SKIPPED, REJECTED or NOTED in an earlier round gets one line instead, `F<k>.<n> = F<j>.<m> (carried)`, and keeps that action even if the reviewer labels its evidence differently; the report lists it once. Holistic-pass findings that repeat a loop finding are cross-referenced, not listed twice; ones that *cause* loop findings become root issues (see Root-cause mapping).

```
F<k>.<n>  <file:line> <summary>
  evidence:   <triggering input/state> — verified-by-running | verified-by-reading | assumption | refuted (<why>)
  siblings:   <search command run> → <matches, or "none">
  root cause: <where the bad state originates> (same place as symptom? yes/no)
  fix shape:  <the correct fix, made at the root cause and every sibling, in one line>
  related:    <is the finding reachable through code the branch changed, or needed for the branch's change to be correct? yes/no>
  intent:     settled (<by which spec line, code, test, doc or domain fact>) | open (<the exact question only the user can answer>)
  contract:   <external contract the fix changes that the branch didn't already change — public API, wire/file format, DB schema or migration, config keys, CLI flags, env vars — or "none">
  behavior:   <observable behavior the fix changes beyond the bug, or "none">
  alternatives: <another defensible fix with different trade-offs, or "none">
  history:    <prior-round finding/commit it touches, or "none">
  action:     AUTO-FIX | DECIDE | ESCALATE | SKIP | REJECT | NOTE
```

Then set `action` with the first matching row. Triage may correct the reviewer's evidence label (e.g. a made-up input labelled verified-by-running) — state why in `evidence`.

| Condition | Action |
|---|---|
| `history` shows it reverts/re-litigates an earlier round's fix | **stop the loop** (oscillation) and ESCALATE both |
| `evidence` is refuted | REJECT, cite the refuting line or run |
| Code is deliberate (comment, docs, ADR, test asserting it) | SKIP, cite the evidence |
| `evidence` is assumption, or it asks for a new feature/parameter | NOTE |
| `related` = no (pre-existing debt the branch neither changes nor relies on) | NOTE |
| `contract` ≠ none | ESCALATE: the contract change, who depends on it, the fix you recommend |
| `intent` is open | ESCALATE: the question, the options, the one you recommend |
| The fix deletes a public function, endpoint, CLI flag or other entry point the branch adds, even one the spec puts out of scope | ESCALATE: keep, cut, or split into its own PR; the author wrote it on purpose |
| `alternatives` ≠ none, or `behavior` ≠ none | DECIDE: pick the fix the code best supports, apply it, record the alternative or behavior change and why |
| Otherwise | AUTO-FIX — at the root cause **and** every sibling |

AUTO-FIX covers fixes of any size: an upstream root-cause fix, consolidating duplicated logic into one helper, changing an internal signature and its callers, removing a symptom guard once its source is fixed, and cleanups (naming, dead code, simplification) on lines the branch touches. A guard is the right fix only when the guarded state is legitimate at its source.

`--report-only`: do round 1 review + triage, then the final holistic pass, then the report (AUTO-FIX and DECIDE findings go under their sections as "would apply, not applied"). Change nothing.

### 3. Fix

For each AUTO-FIX and DECIDE: read the surrounding code and its callers, apply the fix (root cause and all siblings), add a regression test for it if the project has tests (follow the surrounding test style, but don't copy a defect already recorded as a finding), run the tests, and commit it **alone**: `review round <k>: <summary>`, with `[decision]` appended for DECIDE. One commit per finding, so any single fix can be reverted. A file comes off the branch with `git rm --cached`, so it stays on disk.

Tests red after a fix: `git stash push -m "review-until-clean F<k>.<n>"` (do not discard it), mark the finding ESCALATE with the failure output, stop the loop.

### 4. Continue or stop

Stop when any holds: no AUTO-FIX or DECIDE findings this round (converged), round cap reached, tests red, oscillation. Otherwise next round.

## Final holistic pass

Dispatch one more fresh subagent over the **whole** `git diff <base>...HEAD` (the original change plus every fix), asking only design questions: duplicated logic, responsibilities in the wrong module, guards that patch symptoms, accumulated special cases, behavior changes. It reviews with the same concerns as the `simplify` skill but must not invoke it (`simplify` applies fixes) and must not edit. For each finding it states the concrete symptoms the design issue causes (input or state → failure) and the restructure it proposes. Give it no loop findings: it must read the design cold, and the mapping below is your job.

Triage holistic findings with the same record and table. Apply the AUTO-FIX and DECIDE ones as in Fix (one commit each, tests after each). If any were applied, run one more fresh review round over the result (it may exceed `--rounds` by one); apply its AUTO-FIX and DECIDE findings, but do not run another holistic pass.

### Root-cause mapping

Number the holistic findings H1..Hn. For each one, go through every loop finding from every round, whatever its action (AUTO-FIX commits, NOTEs and SKIPs included), and ask: if this design issue were fixed the way H<n> proposes, would the loop finding stop existing, because its trigger becomes impossible or the code it is about goes away? Record:

```
H<n>  <file:line> <design issue>
  determines: F<k>.<m> fully | partly (<what remains>) — <one line: why the restructure removes it>
  moots:      <sha> F<k>.<m> — <an AUTO-FIX commit the restructure would discard or make unnecessary>
```

A holistic finding that determines at least one loop finding (or another holistic finding) is a **root issue**. Rules:
- "Determines" means the proposed restructure removes the finding. Sharing a file, a theme or a symptom is not enough; with no causal link, cross-reference instead.
- A fully determined finding is listed only under its root issue, never again in its own section. A partly determined one is listed under the root issue *and* keeps its residue in its own section, marked `→ partly R<n>`.
- A finding determined by two root issues goes under the one that removes it fully (else the first), with a cross-reference from the other.
- Rank root issues by what they determine: escalated findings first, then the total count. A root issue is reported even if it would have been only a NOTE alone, because what it determines is what makes it matter.
- A root issue you applied (AUTO-FIX or DECIDE) is reported with its commit; one still ESCALATE or NOTE needs the user.

Do not squash. Offer to squash the round commits after the user has read the report.

## Report (exact shape)

```
## review-until-clean: <branch | PR #N | from..to> vs <base> — stopped: <every reason that held: converged, cap, tests red, oscillation> after <k> rounds
Start SHA: <sha>   Tests: <command> → <pass/fail>

### Root issues: fixing one resolves the findings under it
- R<n> (H<m>) <file:line> <design issue> — applied <sha> | needs your decision
  What it causes / restructure (applied or proposed) / what it costs (spec it departs from, churn)
  Resolves: F<k>.<n> (fully | partly: <what remains>) — <why>; H<j> ...
  Moots: <sha> F<k>.<n>

### Needs your decision (ESCALATE)
- F<k>.<n> <file:line> <summary>   [→ partly R<n>]
  The open question or contract change / options / what I recommend

### Decisions I made (DECIDE) — revert any you disagree with
- <sha> F<k>.<n> <summary> — chose <X> over <Y> because <evidence> | behavior change: <what>

### Auto-fixed
- <sha> F<k>.<n> <summary> (siblings: <files or none>)

### Skipped as deliberate / rejected
- F<k>.<n> <summary> — evidence: <comment/doc/test, or refuting line/run>

### Notes (not applied)
- ...

### Holistic pass (design issues that determine no other finding)
- H<n> ... — ESCALATE | NOTE
```

Order matters: "Root issues" comes first, so the user sees the design before its symptoms. Then "Needs your decision" for escalations no root issue fully determines, then "Decisions I made". Omit "Root issues" when there are none, and say so in one line. Then stop and wait; do not act on escalations without the user's choice.

## Ledger (REQUIRED)

When you write the report, append one item line per finding (every action, holistic findings included) to the ledger described in `ledger.md` next to this file. When the user answers an escalation, overrules a decision, or reverts a commit, append an outcome line **before** acting on it. When this skill runs inside `prepare-pr`, use its `run` value.

## Common mistakes

| Mistake | Fix |
|---|---|
| Guarding `None`/null where it crashes | Trace where the null comes from and AUTO-FIX it there; the guard is right only if null is legitimate at the source |
| Fixing one copy of duplicated code | Fix every sibling; when the copies are the same logic, consolidate them (AUTO-FIX) |
| Escalating because the fix is big, structural, upstream, or touches code the branch didn't change | Size is not a reason to ask. ESCALATE needs an open `intent` question or a `contract` change; otherwise AUTO-FIX or DECIDE |
| An ESCALATE that doesn't name the unknown intent or the contract | If you can't write the question only the user can answer, you can answer it: DECIDE |
| Reviewer "cleanup" that changes behavior (caching, retry, ordering) | DECIDE when intent is settled, recording the behavior change; ESCALATE when it is open |
| Second round in the same context says "clean" | Every review is a fresh subagent |
| Batching all fixes in one commit | One commit per finding |
| Auto-fixing a speculative finding ("IPv6 hosts would break") with an `if` on input shape | `evidence: assumption` → NOTE |
| Fixing unrelated debt the review happened to notice | `related: no` → NOTE; the branch's scope stays the branch's scope |
| Removing an out-of-scope feature because "the spec settles it" | The spec settles what to build, not what to throw away: ESCALATE. An unused private helper is still dead code (AUTO-FIX) |
| `git rm` on a scratch or stray file | `git rm --cached`; the user's files stay on disk |
| A design issue listed last under "Holistic pass" while its symptoms fill "Needs your decision" | Root-cause mapping: it becomes a root issue, listed first, with its symptoms nested under it |
| Claiming a root issue resolves a finding because they share a file or theme | "Determines" = the proposed restructure removes the finding's trigger; otherwise cross-reference |
