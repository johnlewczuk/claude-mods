---
name: prepare-pr
description: Use when a feature branch is implemented and the user wants it ready for a pull request — "prepare this for a PR", "get the branch PR-ready", "finish this before review", "clean up before opening the PR".
argument-hint: "[--spec PATH|#ISSUE|none] [--base REF] [--level high] [--rounds N] [--open]"
---

# Prepare PR

## Overview

Takes a finished branch to PR-ready: it does what its spec asks and nothing the spec doesn't, carries nothing that shouldn't ship, is simplified, reviewed until clean and verified, and has a drafted PR body. You leave the branch fixed, not a list of suggestions.

**Decision policy** (the same as `review-until-clean`): fix everything the spec or the code settles, whatever its size. Ask only when the right answer depends on intent nothing written settles, when a fix changes an external contract, or when it needs a history rewrite or a push. Every change is its own commit, and every judgment call is listed in the report, so the user can revert any of them.

## Setup

1. Same preconditions as `review-until-clean`: the session directory is inside the repo, no uncommitted changes to tracked files, not on the default branch. Record the start SHA.
2. Base: `--base`, else the merge-base with the default branch.
3. Spec: `--spec`; else the document the branch was built from: a spec or plan the branch adds or its commits name, `docs/**/specs/` or `docs/**/plans/`, or an issue referenced in the branch name or commits (`gh issue view N`). Several candidates or none: ask once. `none` is a valid answer: skip step 1 and say so in the report.
4. Verification commands (tests, type check, lint, format check, build) from CLAUDE.md and the project's docs, including build-host and no-push rules. Ask once for any that's missing.

## 1. Spec check

Dispatch a fresh subagent (no conversation history) with the spec and `<base>...HEAD`. It reads both in full and returns a two-way map:

```
R<n>  "<requirement, quoted>" — met (<file:line>) | partial (<what's missing>) | missing | deferred (<the spec/plan line deferring it>)
X<n>  <file:line> <code no requirement asks for> — speculative (option nobody sets, parameter nobody passes, abstraction with one implementation, dead branch) | unrequested feature | out of scope (<the spec line excluding it>)
```

Code a requirement needs (tests, plumbing, config it reads) is not an X. Then act:

| Item | Action |
|---|---|
| partial or missing, and the spec says what to build | AUTO-FIX: implement it, with tests. Details it doesn't pin down (which clock, what happens on a delivery failure, behavior when an option is unset) are DECIDE: pick what the spec's wording and the codebase best support, and record it |
| partial or missing, and the spec leaves *what* to build open (two different features would each satisfy it) | ESCALATE: the question, the options, your recommendation |
| deferred | NOTE |
| speculative | AUTO-FIX: remove it |
| unrequested feature, or out of scope | ESCALATE: keep, cut, or split into its own PR (the user may have asked for it outside the spec) |

One commit per item, `prepare-pr: <summary>`; run the tests after each.

## 2. Hygiene

Read `git diff --stat <base>...HEAD` and the full diff for content that shouldn't ship:

| Found | Action |
|---|---|
| Debug output, commented-out code, scratch or try-out files | AUTO-FIX: remove (files: `git rm --cached`, so they stay on disk) |
| Build output, large binaries, lockfile changes without a dependency change, formatting churn on lines the branch had no reason to touch | AUTO-FIX: drop from the branch |
| Planning, spec or scratch-note documents (CLAUDE.md: never committed unless the user said so) | ESCALATE with the proposed history rewrite that drops them from the branch's commits; the files stay on disk |
| Secrets, credentials, `.env`, private keys | ESCALATE first, before anything else; they may need rotating |

Commit the removals, `prepare-pr: hygiene`. Repo housekeeping the branch doesn't cause (a missing `.gitignore`, commit author identity, commit-message wording) is a NOTE, not a question.

## 3. Simplify

Invoke `simplify` with target `<base>..HEAD`, run the tests, and commit its changes as one commit, `prepare-pr: simplify`. Tests red: `git stash push -m "prepare-pr simplify"` (don't discard), note it, continue. Simplify runs before the review loop so the review sees the final shape.

## 4. Review loop

**REQUIRED SUB-SKILL:** invoke `review-until-clean` with `<level> --base <base> --rounds <N> --test "<test command>"` (defaults: `high`, 3 rounds). Its report goes into yours. Its "stop and wait" applies to this whole run: finish steps 5 and 6 first, then stop.

## 5. Verify

**REQUIRED SUB-SKILL:** `superpowers:verification-before-completion`. Run every command from Setup 4 fresh on the final HEAD and record each with its result. Fix failures on lines the branch changed (one commit each) and rerun; anything you can't fix is a blocker.

## 6. PR draft

Write the PR body to the session scratchpad: summary; spec coverage; decisions made; open questions; verification commands and results. Search the issue tracker (`gh issue list --state all --search "<keywords>"`) for issues the branch fixes, partly addresses or invalidates, and reference them (`Fixes #N`, `Refs #N`). End with the session's PR attribution lines.

Open the PR only with `--open` and no blockers (failing checks, open ESCALATE items, secrets): push the branch, then `gh pr create` with the drafted body. Otherwise give the user the command.

## Report (exact shape)

```
## prepare-pr: <branch> vs <base> — READY | READY after your decisions | BLOCKED: <why>
Start SHA: <sha>   Spec: <path | none>

### Needs your decision
- <id> <summary> — question / options / recommendation
  (spec items, then hygiene, then review-until-clean's Root issues and Needs your decision)

### Spec coverage
| R | requirement | status after prepare-pr |

### Decisions I made — revert any you disagree with
- <sha> <summary> — chose <X> over <Y> because <evidence>

### Changes made
- <sha> <summary> — spec | hygiene | simplify | review

### Verification
- <command> → <result>

### Notes
- deferred requirements, NOTE items, anything skipped and why

### PR
<body draft path>; issues referenced: <#N ...>; opened <url> | not opened: <why>
```

## Ledger (REQUIRED)

Use the ledger defined in `~/.claude/skills/review-until-clean/ledger.md`, with one `run` value for the whole run, passed on to `review-until-clean`.
- **Item lines:** when you write the report, append one per spec item (R and X), hygiene item, and simplify commit.
- **Outcome lines:** when the user answers a question, overrules a decision, or reverts a commit, append one **before** acting on it.
- **Retro reminder:** if the ledger holds 5 or more runs since its last `{"type": "retro"}` line, end the report with: `Retro due: <n> runs logged — run /review-retro`.

## Common mistakes

| Mistake | Fix |
|---|---|
| Asking about a missing requirement the spec fully describes | Implement it; the spec settled it |
| Holding a spec item back on a detail question ("which clock should the cooldown use?") | DECIDE the detail, implement, and list the choice |
| Building a deferred or out-of-scope item because it's "nearly done" | Deferred → NOTE; out of scope → ESCALATE |
| Escalating an option nobody sets or a one-implementation interface | Speculative generality: remove it |
| Deleting a stray file from disk | `git rm --cached`; the user's files stay |
| Simplifying after the review loop | Simplify first, so the review sees the final shape |
| Stopping at `review-until-clean`'s report | Finish verification and the PR draft, then report |
| Opening the PR with open escalations or failing checks | Draft only; list the blockers |
