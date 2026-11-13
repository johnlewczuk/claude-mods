from datetime import timedelta

from fleet import devices, rollouts
from fleet.config import load_config
from fleet.util import utcnow

CFG = load_config()


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
    assert rollouts.get_rollout(conn, rid)["status"] == rollouts.DONE


def test_small_percentage_gives_one_device_batches(conn):
    _fleet(conn, n=5)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 10)
    batches = [rollouts.advance(conn, rid) for _ in range(5)]
    assert batches == [0, 1, 2, 3, 4]


def test_advance_records_previous_firmware(conn):
    _fleet(conn)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    rollouts.advance(conn, rid)
    rows = conn.execute(
        "SELECT previous_firmware FROM rollout_devices WHERE rollout_id = ? AND started = 1", (rid,)
    ).fetchall()
    assert [r[0] for r in rows] == ["1.0.0", "1.0.0"]


def test_failures_pause_rollout_and_block_advance(conn):
    _fleet(conn)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    rollouts.advance(conn, rid)
    rollouts.record_result(conn, rid, "lab-0", "failure", CFG)
    assert rollouts.get_rollout(conn, rid)["status"] == rollouts.PAUSED
    assert rollouts.advance(conn, rid) is None


def test_failure_rate_at_threshold_does_not_pause(conn):
    _fleet(conn, n=10)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    rollouts.advance(conn, rid)
    for i, res in enumerate(["success"] * 4 + ["failure"]):
        rollouts.record_result(conn, rid, f"lab-{i}", res, CFG)
    assert rollouts.get_rollout(conn, rid)["status"] == rollouts.RUNNING


def test_failure_rate_before_results_is_zero(conn):
    _fleet(conn)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    assert rollouts.failure_rate(conn, rid) == 0.0


def test_duplicate_result_ignored(conn):
    _fleet(conn)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    rollouts.advance(conn, rid)
    assert rollouts.record_result(conn, rid, "lab-0", "success", CFG) is True
    assert rollouts.record_result(conn, rid, "lab-0", "success", CFG) is False


def test_resume_after_pause(conn):
    _fleet(conn)
    rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
    rollouts.advance(conn, rid)
    rollouts.record_result(conn, rid, "lab-0", "failure", CFG)
    assert rollouts.resume_due(conn, utcnow() + timedelta(hours=1), CFG) == [rid]
