---
name: review-retro
description: Use when the user asks to improve, tune, or run a retrospective on the prepare-pr or review-until-clean skills, or when a prepare-pr report says a retro is due.
---

# Review retro

## Overview

This skill turns the review-skills ledger into tested edits to `review-until-clean` and `prepare-pr`.

**Core principle:** a lesson changes a skill only when two things hold. Evidence from real runs shows a pattern, and an eval case reproduces the pattern, fails on the current skill, and passes on the edited one without regressing the rest of the suite. A single incident is an anecdote, not a pattern.

**Paths.** The skills and their evals live in `~/repos/claude-mods`: `skills/` holds the skills and `evals/` holds the suite. Read `evals/README.md` first. The ledger format is in `skills/review-until-clean/ledger.md`.

## 1. Collect

1. Read the ledger lines that come after the last `{"type": "retro"}` line.
2. Find outcomes that were never recorded. For each run whose repo still exists:
   - **Reverts:** a commit whose message contains `This reverts commit <sha>`, for a `commit` named in an item line. Append `reverted`.
   - **PR follow-up:** check for a GitHub remote and a PR for the branch (`gh pr list --head <branch> --state all`). If one exists, read its review comments (`gh pr view N --comments`, plus `gh api repos/{owner}/{repo}/pulls/N/comments`) and any commits made after the run. Something there that the run should have reported becomes an outcome line: `missed`, item `M<n>`, with a category.
3. Append the outcome lines you found. Never edit existing lines.

## 2. Find patterns

Group by `category × action`, then apply these thresholds:

| Pattern | Threshold | Lesson |
|---|---|---|
| Unneeded questions | ESCALATE in a category: ≥ 3 answered and ≥ 80 % `accepted-recommendation` | That class should be DECIDE (or AUTO-FIX) |
| Too bold | AUTO-FIX/DECIDE in a category: ≥ 2 `reverted`, or ≥ 25 % reverted | That class needs ESCALATE, or a narrower rule |
| Wrong default | ≥ 2 `chose-other` in the same direction | Change which option is recommended or chosen |
| Blind spot | ≥ 2 `missed` in a category | Add it to the reviewer's or spec-check brief |

Report the patterns that fall short of a threshold too, as "watching" lines. Don't act on them.

## 3. Turn each lesson into a tested edit

For each lesson:

1. **Build the eval case first.** Make the smallest fixture or triage case that reproduces the real incident.
   - It must be anonymized. The repo is public, so it must not contain project, customer, product or person names, or real code. Rewrite the incident in a neutral domain.
   - Add rows to an answer key, with the Expected, Also OK and Forbidden actions.
2. **Watch it fail.** Run the case on the current skill. If it already passes, the ledger pattern has a different cause: look again before changing anything.
3. **Write the edit.** Make the smallest change that fixes it: a table row, a common-mistakes row, or tighter wording. **REQUIRED SUB-SKILL:** superpowers:writing-skills ("Match the Form to the Failure"; no nuance clauses).
4. **Watch it pass, and check for regressions.**
   - Triage-level edits: run `evals/run-triage.sh <case> 3` for the new case and every existing triage case.
   - Edits that change full runs: `run-eval.sh` costs real money. Ask the user before running it, and give the estimated cost from `evals/README.md`.

## 4. Present and apply

For each lesson, show the user:
- the evidence: counts, and two or three anonymized example items
- the edit as a diff
- the eval results before and after

Apply only the lessons the user approves. Commit them in `~/repos/claude-mods` on a branch, one commit per lesson, with the eval case in the same commit. Never push unless the user asks.

Finally, append `{"type": "retro", "ts": "<ISO time>", "lessons": ["<one line each>"], "watching": ["..."]}` to the ledger.

## Common mistakes

| Mistake | Fix |
|---|---|
| Editing a skill because of one bad run | Wait for the threshold; record the run as a "watching" line |
| Adding a rule without an eval case | Case first; it has to fail before the edit |
| Copying the real incident into the eval | Rewrite it neutrally; the repo is public |
| A fix for one lesson that regresses another case | Run the whole triage suite, not just the new case |
| Deleting or rewriting ledger lines | Append only |
