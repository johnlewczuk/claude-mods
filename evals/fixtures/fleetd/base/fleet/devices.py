"""Device registry."""
import re

from . import db
from .http import json_response

GROUP_NAME = re.compile(r"^[a-z0-9-]{1,32}$")


def create_group(conn, name):
    if not GROUP_NAME.match(name):
        raise ValueError(f"invalid group name: {name!r}")
    conn.execute("INSERT INTO device_groups (name) VALUES (?)", (name,))
    conn.commit()


def register_device(conn, device_id, group, firmware):
    conn.execute(
        "INSERT INTO devices (id, group_name, firmware) VALUES (?, ?, ?)",
        (device_id, group, firmware),
    )
    conn.commit()


def list_devices(conn, groups=None):
    """All devices, optionally only those in the given groups, ordered by id."""
    if not groups:
        return db.query(conn, "SELECT * FROM devices ORDER BY id")
    marks = ",".join("?" for _ in groups)
    return db.query(
        conn, f"SELECT * FROM devices WHERE group_name IN ({marks}) ORDER BY id", tuple(groups)
    )


def serialize(device):
    return {
        "id": device["id"],
        "group": device["group_name"],
        "firmware": device["firmware"],
        "last_seen": device["last_seen"],
    }


def handle_list_devices(conn, req):
    group = req.query.get("group")
    found = list_devices(conn, [group] if group else None)
    return json_response({"devices": [serialize(d) for d in found]})
