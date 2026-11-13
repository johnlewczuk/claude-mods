CREATE TABLE rollouts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    firmware TEXT NOT NULL,
    groups TEXT NOT NULL,              -- comma-separated group names
    batch_percent INTEGER NOT NULL,
    status TEXT NOT NULL DEFAULT 'pending',
    paused_at TEXT,
    created_at TEXT NOT NULL
);

CREATE TABLE rollout_devices (
    rollout_id INTEGER NOT NULL REFERENCES rollouts(id),
    device_id TEXT NOT NULL REFERENCES devices(id),
    batch INTEGER NOT NULL,
    started INTEGER NOT NULL DEFAULT 0,
    previous_firmware TEXT,
    result TEXT,
    PRIMARY KEY (rollout_id, device_id)
);

ALTER TABLE devices ADD COLUMN target_firmware TEXT;
