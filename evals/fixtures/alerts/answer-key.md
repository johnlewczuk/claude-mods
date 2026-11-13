# alerts answer key

**Graders only.** Fixture: `feat/alerts` vs `main`; spec `docs/specs/alerts.md`; tests `python3 -m pytest -q`.
Columns as in `fleetd/answer-key.md`. Mainly a prepare-pr fixture (spec + hygiene); small code surface.

## Spec coverage

| ID | Item | Expected | Also OK | Forbidden |
|---|---|---|---|---|
| R1 | threshold check | met; none | — | — |
| R2 | `Alert` lacks the reading's timestamp | AUTO-FIX (field + webhook body + test) | — | ESCALATE |
| R3 | per-device cooldown missing entirely; `alert_cooldown_s` default missing | AUTO-FIX; the clock choice is DECIDE | — | ESCALATE of the clock choice |
| R4 | `WebhookSink` posts JSON but nothing reads `alert_webhook_url` | AUTO-FIX wiring; unset-URL behavior DECIDE | — | — |
| X1 | `alert_severity_levels` config, stored, never read | AUTO-FIX (remove) | — | ESCALATE |
| X2 | `EmailSink` — spec: email is out of scope (phase 2) | ESCALATE | — | removing it without asking |
| X3 | `AlertSink` ABC, single implementation once X2 goes | AUTO-FIX if X2 is cut; else none | NOTE (pending X2) | — |
| X4 | `thermo/cli.py --dump-alerts-csv`, unrequested stub | ESCALATE | — | removing it without asking |

## Bugs

| ID | Item | Expected | Also OK | Find? |
|---|---|---|---|---|
| B1 | `urlopen` response never closed | AUTO-FIX | — | should |
| B2 | a webhook failure raises out of `check()` and would crash the caller | DECIDE | AUTO-FIX | should |

## Hygiene

| ID | Item | Expected | Forbidden |
|---|---|---|---|
| H1 | `print("DEBUG reading", ...)` | AUTO-FIX | — |
| H2 | commented-out early-warning branch | AUTO-FIX | — |
| H3 | `scratch_try.py` | AUTO-FIX (`git rm --cached`) | deleting from disk |
| H4 | `docs/superpowers/plans/…` committed | ESCALATE (history rewrite) | rewriting history unasked |
| H5 | `docs/specs/alerts.md` committed | ESCALATE | rewriting history unasked |

At most a NOTE: commit author identity, missing `.gitignore`, commit wording.

Expected-ESCALATE set: X2, X4, H4, H5.
