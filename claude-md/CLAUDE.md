# Global Claude Instructions

## Plain language

No jargon in anything you write: replies, commit messages, PR and issue text,
docs and code comments. Say what you mean in ordinary words.

The words below are examples, not a complete list. Avoid all jargon, not only
these words: if a plainer word says the same thing, use it.

- Never say "bench". Name the actual thing: "on the device", "on
  the test board", "a hardware test", "with the real camera".
- Never say "stamp" or "stamped". Say what happens: "filled in with the
  camera id", "one copy per camera", "written into".
- Never say "brief" for a task or what it asks for. Say what it is: "what you
  asked for", "the requirements", "the mock".

An existing name in code or paths (e.g. a `bench/` directory) may be quoted as
the name it is, in backticks; don't use it as a word of your own.

## Repositories and machine notes

Where the repositories live and their build rules are kept in a private
file outside this repo:

@~/.claude/CLAUDE.private.md

## Software development practices

- Edits must never make the code less clean. If the straightforward change
  would add hacks, duplication, special cases, or otherwise degrade the design,
  make the clean change instead, even if it is larger or touches more code.
  Ask first only when the clean change alters an external contract (public
  API, wire/file format, DB schema, config keys, CLI), depends on intent the
  spec, code, tests and docs don't settle, or is a redesign well beyond what
  the task asked for. When you make a judgment call, say so in your report,
  with the alternative you rejected.
- Do clear, simple tasks directly (copying files, syncing configs, a small
  fix). Save the brainstorm, spec, plan and review steps for real design work.
- Don't design around a limit nobody has confirmed. Mention a suspected limit
  once, in a line, with what would confirm it, and keep the simple design
  until the user says the limit is real.
- When the user supplies a mock, keep its colours, fonts and shapes. Fix only
  what they complain about. If research or a design skill argues for a
  different look, say what it recommends and let the user choose.

## Development tools

Install development and debugging tools (OpenOCD, toolchains, analyzers, Python
packages for them) inside the project's Docker image or container, not on the
host. If a project has no Docker setup, ask before installing on the host.

## Committing planning/spec documents

Do not commit planning or spec documents (plans, design docs, specs, scratch
notes, including anything under `docs/superpowers/`) unless the user explicitly
asks. The user keeps these out of version history.

## Pull Requests

**Every PR must stay focused on one change. No exceptions.** If you find a fix
that is unrelated, or only partly related, to what the PR is for, do not add
it. Put it in a separate PR (or note it for one). Keep PRs small and easy to
read where you can; when size and focus pull apart, focus wins.

When creating a PR, search the repo's issue tracker for issues the change
fixes, partly addresses, or makes obsolete, and reference them in the PR
description (e.g. `Fixes #123`, `Refs #456`).

Every PR description includes a **Suggested reading order**: a numbered list of
`file:function` entries, each with a one-line note on what to look for there.

- Start with one or more **entrypoints**: the functions where the new behaviour
  begins at runtime (a request handler, a reconcile loop, a node's `Process`, a
  CLI command). Use more than one when the change has independent triggers. From
  an entrypoint a reviewer learns what the change is for before reading how it
  works.
- Then follow the call path outward: what the entrypoint calls, in the order it
  calls them.
- Put helpers, pure functions, data types and tests last. A file of pure
  functions (e.g. `camera_chain.cpp`) means little until its caller shows why
  it exists.
- Leave out mechanical edits (a signature change repeated across files, renames).
  One closing line covering them as a group is enough.

## GitHub Issues

When creating GitHub issues, always add a label when a relevant one already
exists.

## Port Registry

When starting, configuring, or creating a server or service that listens on a
port, always update `~/.ports.csv` with an entry for it. The file format is:

```
PORT | SOFTWARE | LOCATION | HAS_FRONTEND
```

- **PORT**: The port number being used
- **SOFTWARE**: What software/service is running (e.g. "Docsify via python3 http.server")
- **LOCATION**: Absolute path to the project directory the server runs from
- **HAS_FRONTEND**: `yes` or `no` — whether the service has a web UI (affects dashboard display)

Before assigning a port, check `~/.ports.csv` for conflicts. When removing a
server, remove its entry from the file.

## Obsidian Vault

The user's Obsidian vault is located at `~/Documents/Obsidian Vault/`.

### Note Structure

Every Obsidian note must start with YAML frontmatter:

```yaml
---
date: YYYY-MM-DD
---
```

Rules:
- **Frontmatter is mandatory** — always include `date` (YYYY-MM-DD format, set to creation date)
- **Links**: Use `[[wikilinks]]` to connect related notes. Before finishing any note, scan existing notes in the vault and link to every relevant one. This is the most important rule — notes without links are isolated and lose most of their value.
- **Attachments**: Place images and media in `Attachments/` (create it if it doesn't exist yet)

### Debugging Lessons

`Debugging Lessons.md` in the vault is the user's log of hard bugs. Since
Claude does most of the debugging, the note keeps the reasoning and technique
for the user, not just the fix. At the end of a session that cracked a
non-obvious bug, offer once to log it; don't add entries unasked. When asked,
add an entry at the top of `## Log` using the template at the bottom of the
note, add any reusable technique to `## Techniques toolbox`, and link related
notes.

## Vocalize physical actions

When a task needs the user to act physically or off-terminal (button press,
cable plug/unplug, power-cycle, boot mode, read an LED, phone 2FA), run
`vocalize "<one short sentence>"` before waiting, and still give full details in
text. See the `vocalize` skill.

## Long hardware tests: batch them, never mid-loop

Do not run long hardware tests during the development loop without the user's
explicit permission. "Long" means anything that holds a device or waits on wall
time beyond a few minutes: soak or idle tests, 30-minute waits, overnight
stability runs, long recordings.

Instead, record each one in a deferred-tests list kept with the work's notes
(e.g. the plan's ledger), with its exact steps, the device it needs, its
duration, and its pass criteria. Then they can be run as one batch, overnight
or over a weekend. Short checks on the device (minutes) can run in the loop as
usual. Say which long tests you deferred when you report.

## Check on long-running work yourself

Run work you will wait on (a subagent, a build or test run, a remote job) in
the background, and wait on the task itself: act on its completion
notification the moment it arrives. The timer below is only a backstop for a
missed notification. Never let it set the pace.

Work that runs detached sends no notification of its own (`nohup … &`, a
container started in a subshell, a job on another machine). For it, start a
background shell that waits on the job and prints the result, e.g.
`while kill -0 $pid; do sleep 10; done; cat result`, or a loop on the result
file or log line. That shell's exit is the notification.

Completion notifications (subagent reports, background-shell exits, monitors)
are sometimes missed or never sent, and a missed one stalls the work silently.
So alongside every background task, also set a backstop timer:

1. Estimate how long it should take, add a buffer (about 50%, at least 5
   minutes), and start a background `sleep <seconds>; echo "check <task>"`
   shell (it re-invokes you when it exits).
2. If the task's notification arrives first, kill its timer immediately (e.g.
   TaskStop on the sleep shell), then handle the result right away. Don't
   leave a stale timer running to wake you later.
3. If the timer fires first, check the task's real state directly: the
   process list, the log tail, the result or report file, the commit. If it is
   done, act on it. If it is still making progress, set another timer from a
   fresh estimate. If it is stuck or idle without having finished (e.g. an
   agent that stopped without writing its report), nudge or restart it.
