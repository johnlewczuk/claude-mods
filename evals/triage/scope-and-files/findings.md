# Branch under review: `feat/export-jobs` (Python service, base `main`)

The branch adds scheduled export jobs. Spec (docs/specs/exports.md, excerpt):
"E1. Operators schedule a nightly CSV export of the inventory table to a configured
directory. E2. Each run writes one file named `inventory-<date>.csv`.
Out of scope for this change: exporting to S3 (planned for phase 2)."

Files the branch changed: app/exports.py (new), app/scheduler.py (modified),
tests/test_exports.py (new), try_export.py (new, repo root). Tests: `python3 -m pytest -q` passes.

Round 1 findings from the reviewer subagent (evidence labels as reported):

F1.1 app/exports.py:88-120 — `upload_to_s3(path, bucket)` is a public function the branch adds;
nothing calls it, it is not wired to the scheduler, and the spec puts S3 export out of scope
(phase 2). It also never closes the boto session. — verified-by-reading

F1.2 try_export.py — a scratch script at the repo root that runs one export against a
hard-coded local path; committed by the branch, imported by nothing. — verified-by-reading

F1.3 app/exports.py:40 — `_format_row_legacy(row)` is a private helper the branch adds that
nothing calls (superseded by `_format_row` at line 31). — verified-by-reading

F1.4 app/exports.py:55 — the export file is opened with `open(path, "w")` and never closed if
`writer.writerows` raises; data can be left unflushed. — verified-by-reading
