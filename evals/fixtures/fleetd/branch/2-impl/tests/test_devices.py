import pytest

from fleet import devices
from fleet.http import Request


def test_list_devices_by_group(conn):
    devices.create_group(conn, "lab")
    devices.create_group(conn, "field")
    devices.register_device(conn, "d1", "lab", "1.0.0")
    devices.register_device(conn, "d2", "field", "1.0.0")
    assert [d["id"] for d in devices.list_devices(conn, ["lab"])] == ["d1"]
    assert len(devices.list_devices(conn)) == 2


def test_invalid_group_name_rejected(conn):
    with pytest.raises(ValueError):
        devices.create_group(conn, "Bad Name")


def test_handle_list_devices(conn):
    devices.create_group(conn, "lab")
    devices.register_device(conn, "d1", "lab", "1.0.0")
    resp = devices.handle_list_devices(conn, Request("GET", "/devices", query={"group": "lab"}))
    assert resp.status == 200
    assert '"groups": ["lab"]' in resp.body
