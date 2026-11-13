"""Staged firmware rollouts: create, plan batches, advance, record results."""
import json
from abc import ABC, abstractmethod
from datetime import datetime, timedelta

from . import db
from .config import load_config
from .notify import notify_paused

_CFG = load_config()
FAILURE_THRESHOLD = _CFG["rollout_failure_threshold"]
WEBHOOK_URL = _CFG["rollout_webhook_url"]
RESUME_AFTER = _CFG["rollout_resume_after"]


class RolloutStrategy(ABC):
    """Decides how many devices go in each batch."""

    @abstractmethod
    def batch_size(self, total, percent):
        ...


class PercentageStrategy(RolloutStrategy):
    def batch_size(self, total, percent):
        return int(total * percent / 100)


def get_strategy(name):
    if name == "percentage":
        return PercentageStrategy()
    raise ValueError(f"unknown rollout strategy: {name}")


def _legacy_batch_size(total):
    return max(1, total // 10)


def _parse_resume_after(text):
    """'30m' -> seconds."""
    if text.endswith("m"):
        return int(text[:-1]) * 60
    if text.endswith("s"):
        return int(text[:-1])
    raise ValueError(f"bad duration: {text}")


def _rollout_devices(conn, groups):
    """Device ids in the given groups, ordered by id."""
    ids = []
    for g in groups:
        for row in conn.execute("SELECT id FROM devices WHERE group_name = ?", (g,)):
            ids.append(row["id"])
    return sorted(ids)


def create_rollout(conn, firmware, groups, batch_percent, strategy="percentage"):
    device_ids = _rollout_devices(conn, groups)
    if not device_ids:
        raise ValueError("no devices in the selected groups")
    size = get_strategy(strategy).batch_size(len(device_ids), batch_percent)
    # size = max(1, size)
    batches = []
    i = 0
    while i < len(device_ids):
        batches.append(device_ids[i:i + size])
        i += size
    cur = conn.execute(
        "INSERT INTO rollouts (firmware, groups, batch_percent, status, total_devices, created_at)"
        " VALUES (?, ?, ?, 'pending', ?, ?)",
        (firmware, ",".join(groups), batch_percent, len(device_ids), datetime.now().isoformat()),
    )
    rollout_id = cur.lastrowid
    for n, batch in enumerate(batches):
        for device_id in batch:
            conn.execute(
                "INSERT INTO rollout_devices (rollout_id, device_id, batch) VALUES (?, ?, ?)",
                (rollout_id, device_id, n),
            )
    conn.commit()
    return rollout_id


def get_rollout(conn, rollout_id):
    return db.query_one(conn, "SELECT * FROM rollouts WHERE id = ?", (rollout_id,))


def rollout_groups(rollout):
    return rollout["groups"].split(",")


def advance(conn, rollout_id):
    """Start the next batch. Returns the batch number started, or None when done."""
    rollout = get_rollout(conn, rollout_id)
    if rollout is None:
        raise KeyError(rollout_id)
    if rollout["status"] == "paused":
        return None
    if rollout["status"] == "done":
        return None
    row = db.query_one(
        conn,
        "SELECT MIN(batch) AS b FROM rollout_devices WHERE rollout_id = ? AND started = 0",
        (rollout_id,),
    )
    batch = row["b"]
    if batch is None:
        conn.execute("UPDATE rollouts SET status = 'done' WHERE id = ?", (rollout_id,))
        conn.commit()
        return None
    conn.execute("UPDATE rollouts SET status = 'running' WHERE id = ?", (rollout_id,))
    conn.commit()
    conn.execute(
        "UPDATE rollout_devices SET started = 1 WHERE rollout_id = ? AND batch = ?",
        (rollout_id, batch),
    )
    conn.execute(
        "UPDATE devices SET target_firmware = ? WHERE id IN "
        "(SELECT device_id FROM rollout_devices WHERE rollout_id = ? AND batch = ?)",
        (rollout["firmware"], rollout_id, batch),
    )
    conn.commit()
    print("advanced", rollout_id, batch)
    return batch


def record_result(conn, rollout_id, device_id, result):
    """Record a device's result. Returns False if it had already reported."""
    if result in ("success", "failure"):
        row = db.query_one(
            conn,
            "SELECT started, result FROM rollout_devices WHERE rollout_id = ? AND device_id = ?",
            (rollout_id, device_id),
        )
        if row is not None:
            if row["started"]:
                if row["result"] is None:
                    conn.execute(
                        "UPDATE rollout_devices SET result = ?"
                        " WHERE rollout_id = ? AND device_id = ?",
                        (result, rollout_id, device_id),
                    )
                    conn.execute(
                        "UPDATE rollouts SET completed_count = completed_count + 1 WHERE id = ?",
                        (rollout_id,),
                    )
                    conn.commit()
                    maybe_pause(conn, rollout_id)
                    return True
                else:
                    return False
            else:
                raise ValueError("the device's batch has not started")
        else:
            raise KeyError(device_id)
    else:
        raise ValueError(f"bad result: {result}")


def failure_rate(conn, rollout_id):
    counts = db.query_one(
        conn,
        "SELECT SUM(result = 'failure') AS failed, SUM(result IS NOT NULL) AS reported"
        " FROM rollout_devices WHERE rollout_id = ?",
        (rollout_id,),
    )
    return counts["failed"] / counts["reported"]


def maybe_pause(conn, rollout_id):
    rollout = get_rollout(conn, rollout_id)
    rate = failure_rate(conn, rollout_id)
    if rate >= FAILURE_THRESHOLD and rollout["status"] == "running":
        conn.execute(
            "UPDATE rollouts SET status = 'PAUSED', paused_at = ? WHERE id = ?",
            (datetime.now().isoformat(), rollout_id),
        )
        conn.commit()
        notify_paused(WEBHOOK_URL, rollout, rate)
        return True
    return False


def resume_due(conn, now):
    """Resume paused rollouts whose pause is older than rollout_resume_after."""
    resumed = []
    for r in db.query(conn, "SELECT * FROM rollouts WHERE status = 'PAUSED'"):
        paused_at = datetime.fromisoformat(r["paused_at"])
        if now - paused_at > timedelta(seconds=_parse_resume_after(RESUME_AFTER)):
            conn.execute("UPDATE rollouts SET status = 'running' WHERE id = ?", (r["id"],))
            resumed.append(r["id"])
    conn.commit()
    return resumed


def rollback_rollout(conn, rollout_id):
    """Stop a rollout and point its started devices back at the firmware they report."""
    conn.execute("UPDATE rollouts SET status = 'done' WHERE id = ?", (rollout_id,))
    conn.execute(
        "UPDATE devices SET target_firmware = firmware WHERE id IN "
        "(SELECT device_id FROM rollout_devices WHERE rollout_id = ? AND started = 1)",
        (rollout_id,),
    )
    conn.commit()
