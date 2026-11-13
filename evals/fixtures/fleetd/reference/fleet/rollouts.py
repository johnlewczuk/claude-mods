"""Staged firmware rollouts: create, plan batches, advance, record results."""
import math
from datetime import datetime

from . import db
from .devices import list_devices
from .notify import notify_paused
from .util import chunked, parse_duration, utcnow

PENDING, RUNNING, PAUSED, DONE = "pending", "running", "paused", "done"
STATUSES = (PENDING, RUNNING, PAUSED, DONE)


def create_rollout(conn, firmware, groups, batch_percent):
    device_ids = [d["id"] for d in list_devices(conn, groups)]
    if not device_ids:
        raise ValueError("no devices in the selected groups")
    size = max(1, math.ceil(len(device_ids) * batch_percent / 100))
    with db.transaction(conn):
        rollout_id = conn.execute(
            "INSERT INTO rollouts (firmware, groups, batch_percent, status, created_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (firmware, ",".join(groups), batch_percent, PENDING, utcnow().isoformat()),
        ).lastrowid
        for n, batch in enumerate(chunked(device_ids, size)):
            conn.executemany(
                "INSERT INTO rollout_devices (rollout_id, device_id, batch) VALUES (?, ?, ?)",
                [(rollout_id, device_id, n) for device_id in batch],
            )
    return rollout_id


def get_rollout(conn, rollout_id):
    return db.query_one(conn, "SELECT * FROM rollouts WHERE id = ?", (rollout_id,))


def list_rollouts(conn, status=None):
    if status is None:
        return db.query(conn, "SELECT * FROM rollouts ORDER BY id")
    return db.query(conn, "SELECT * FROM rollouts WHERE status = ? ORDER BY id", (status,))


def advance(conn, rollout_id):
    """Start the next batch. Returns the batch number started, or None if none was."""
    rollout = get_rollout(conn, rollout_id)
    if rollout is None:
        raise KeyError(rollout_id)
    if rollout["status"] in (PAUSED, DONE):
        return None
    batch = db.query_one(
        conn,
        "SELECT MIN(batch) AS b FROM rollout_devices WHERE rollout_id = ? AND started = 0",
        (rollout_id,),
    )["b"]
    with db.transaction(conn):
        if batch is None:
            conn.execute("UPDATE rollouts SET status = ? WHERE id = ?", (DONE, rollout_id))
            return None
        conn.execute("UPDATE rollouts SET status = ? WHERE id = ?", (RUNNING, rollout_id))
        conn.execute(
            "UPDATE rollout_devices SET started = 1, previous_firmware ="
            " (SELECT firmware FROM devices WHERE devices.id = rollout_devices.device_id)"
            " WHERE rollout_id = ? AND batch = ?",
            (rollout_id, batch),
        )
        conn.execute(
            "UPDATE devices SET target_firmware = ? WHERE id IN"
            " (SELECT device_id FROM rollout_devices WHERE rollout_id = ? AND batch = ?)",
            (rollout["firmware"], rollout_id, batch),
        )
    return batch


def record_result(conn, rollout_id, device_id, result, cfg):
    """Record a device's result. Returns False if it had already reported."""
    if result not in ("success", "failure"):
        raise ValueError(f"bad result: {result}")
    row = db.query_one(
        conn,
        "SELECT started, result FROM rollout_devices WHERE rollout_id = ? AND device_id = ?",
        (rollout_id, device_id),
    )
    if row is None:
        raise KeyError(device_id)
    if not row["started"]:
        raise ValueError("the device's batch has not started")
    if row["result"] is not None:
        return False
    with db.transaction(conn):
        conn.execute(
            "UPDATE rollout_devices SET result = ? WHERE rollout_id = ? AND device_id = ?",
            (result, rollout_id, device_id),
        )
    maybe_pause(conn, rollout_id, cfg)
    return True


def failure_rate(conn, rollout_id):
    counts = db.query_one(
        conn,
        "SELECT COUNT(*) FILTER (WHERE result = 'failure') AS failed,"
        " COUNT(result) AS reported FROM rollout_devices WHERE rollout_id = ?",
        (rollout_id,),
    )
    return counts["failed"] / counts["reported"] if counts["reported"] else 0.0


def maybe_pause(conn, rollout_id, cfg):
    rollout = get_rollout(conn, rollout_id)
    rate = failure_rate(conn, rollout_id)
    if rollout["status"] != RUNNING or rate <= cfg["rollout_failure_threshold"]:
        return False
    with db.transaction(conn):
        conn.execute(
            "UPDATE rollouts SET status = ?, paused_at = ? WHERE id = ?",
            (PAUSED, utcnow().isoformat(), rollout_id),
        )
    notify_paused(cfg["rollout_webhook_url"], rollout, rate)
    return True


def resume_due(conn, now, cfg):
    """Resume paused rollouts whose pause is older than rollout_resume_after."""
    resume_after = parse_duration(cfg["rollout_resume_after"])
    resumed = []
    with db.transaction(conn):
        for r in list_rollouts(conn, PAUSED):
            if now - datetime.fromisoformat(r["paused_at"]) > resume_after:
                conn.execute("UPDATE rollouts SET status = ? WHERE id = ?", (RUNNING, r["id"]))
                resumed.append(r["id"])
    return resumed


def rollback_rollout(conn, rollout_id):
    """Stop a rollout and point its started devices back at the firmware they report."""
    with db.transaction(conn):
        conn.execute("UPDATE rollouts SET status = ? WHERE id = ?", (DONE, rollout_id))
        conn.execute(
            "UPDATE devices SET target_firmware = firmware WHERE id IN"
            " (SELECT device_id FROM rollout_devices WHERE rollout_id = ? AND started = 1)",
            (rollout_id,),
        )
