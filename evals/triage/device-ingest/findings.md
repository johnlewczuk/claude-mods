# Branch under review: `feat/device-ingest` (Go service, base `main`)

The branch adds a device telemetry ingest endpoint. Spec (docs/specs/ingest.md, excerpt):
"POST /v1/ingest accepts a batch of readings from a device. Transient upstream failures
(timeouts, 5xx) are retried with backoff. The endpoint is documented in api/openapi.yaml."

Files the branch changed: internal/ingest/handler.go (new), internal/ingest/batch.go (new),
internal/ingest/store.go (new), internal/config/config.go (modified), api/openapi.yaml (modified).
Tests: `go test ./...` passes.

Round 1 findings from the reviewer subagent (evidence labels as reported):

F1.1 internal/ingest/handler.go:58 — nil pointer dereference on `reading.Meta.Site` when a device
sends a reading with no metadata. The nil comes from `parse.Reading()` in internal/parse/reading.go:31
(NOT changed by the branch), which returns `Meta: nil` for empty input instead of a zero-value Meta.
Two other callers of parse.Reading() (internal/export/csv.go:44, internal/alerts/eval.go:12) already
nil-check Meta. Fixing it means making parse.Reading return `&Meta{}` and removing the two existing
nil checks. — verified-by-running (curl with `{"readings":[{"v":1}]}` → 500 panic)

F1.2 internal/ingest/batch.go:20-41 and internal/ingest/store.go:88-110 — the same reading-validation
logic (range check, timestamp skew check) is implemented twice in the branch's new files, with one
difference: batch.go allows 5 min clock skew, store.go allows 300 s (equivalent). A fix would extract
one `validateReading()` helper in batch.go and call it from both. — verified-by-reading

F1.3 internal/ingest/store.go:130 — upstream write retries on every error, including 4xx responses
(e.g. 400 schema rejection), retrying forever with backoff. Fix: retry only on timeouts and 5xx;
return 4xx errors immediately. This changes observable behavior (4xx batches now fail fast instead of
hanging). — verified-by-reading

F1.4 internal/config/config.go:77 — the branch renamed config key `ingest_timeout` to
`ingest_timeout_ms` (value now in ms). Existing deployments' config files that set `ingest_timeout`
will silently fall back to the default. Fix options: accept the old key with a deprecation warning,
or keep the rename and document it in release notes. — verified-by-reading

F1.5 internal/ingest/handler.go:102 — host parsing with `strings.Split(addr, ":")` would break on IPv6
literal addresses. All configs and the device firmware use IPv4 hostnames; nothing produces IPv6.
— assumption

F1.6 internal/legacy/report.go:210 — SQL built with string concatenation of a query parameter
(possible SQL injection). The file is not changed by the branch and is not called by the ingest code.
— verified-by-reading

F1.7 internal/ingest/batch.go:5 — unused import `sort` in a new file (compiles because it is used in a
`_ = sort.Ints` line left over from debugging). — verified-by-reading

F1.8 internal/ingest/handler.go:140 — when a device ID is unknown the endpoint returns 200 with
`{"accepted":0}`. Reviewer suggests 404. api/openapi.yaml (changed by this branch) documents the
200 `{"accepted":0}` response, and the device firmware team consumes this API. — verified-by-reading
