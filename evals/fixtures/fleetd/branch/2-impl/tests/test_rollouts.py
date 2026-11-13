from datetime import datetime, timedelta

from fleet import devices, rollouts


def _fleet(conn, n=4, group="lab"):
    devices.create_group(conn, group)
    for i in range(n):
        devices.register_device(conn, f"{group}-{i}", group, "1.0.0")


def test_create_and_advance(conn):
    _fleet(conn)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    assert rollouts.advance(conn, rid) == 0
    assert rollouts.advance(conn, rid) == 1
    assert rollouts.advance(conn, rid) is None
    assert rollouts.get_rollout(conn, rid)["status"] == "done"


def test_failures_pause_rollout(conn):
    _fleet(conn)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    rollouts.advance(conn, rid)
    rollouts.record_result(conn, rid, "lab-0", "failure")
    assert rollouts.get_rollout(conn, rid)["status"] == "PAUSED"


def test_duplicate_result_ignored(conn):
    _fleet(conn)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    rollouts.advance(conn, rid)
    assert rollouts.record_result(conn, rid, "lab-0", "success") is True
    assert rollouts.record_result(conn, rid, "lab-0", "success") is False


def test_resume_after_pause(conn):
    _fleet(conn)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    rollouts.advance(conn, rid)
    rollouts.record_result(conn, rid, "lab-0", "failure")
    later = datetime.now() + timedelta(hours=1)
    assert rollouts.resume_due(conn, later) == [rid]
