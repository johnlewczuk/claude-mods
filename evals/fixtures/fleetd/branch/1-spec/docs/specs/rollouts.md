# Staged firmware rollouts

R1. An operator creates a rollout for a firmware version and one or more device groups
    (`POST /rollouts` with `{"firmware": ..., "groups": [...], "batch_percent": N}`).
    The response is 202 Accepted with the rollout id; no device is touched until the
    first batch is started.
R2. The rollout's devices are split into batches of `batch_percent` percent of the
    rollout's devices, rounded up; every batch contains at least one device.
R3. `advance` starts the next batch: for each device in the batch it records the firmware
    version the device had before, points the device at the new firmware, and marks the
    batch started. All of this happens atomically.
R4. Devices report a result (`success` or `failure`). When the failure rate among the
    rollout's reported results exceeds `rollout_failure_threshold` (config, default 0.2),
    the rollout is paused and the webhook at `rollout_webhook_url` is notified.
R5. `GET /rollouts?status=<status>` lists rollouts, optionally filtered by status
    (`pending`, `running`, `paused`, `done`). `GET /rollouts/<id>` returns one rollout
    with its current failure rate.
R6. API errors use the shared error shape (`{"error": ...}`) with a 4xx/5xx status.

Out of scope for this change: rolling devices back to their previous firmware (phase 2).
