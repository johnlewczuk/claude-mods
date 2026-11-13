CREATE TABLE device_groups (
    name TEXT PRIMARY KEY
);

CREATE TABLE devices (
    id TEXT PRIMARY KEY,
    group_name TEXT NOT NULL REFERENCES device_groups(name),
    firmware TEXT NOT NULL,
    last_seen TEXT
);
