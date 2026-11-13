from fleet import db, devices, rollouts

conn = db.connect(":memory:")
db.migrate(conn, "migrations")
devices.create_group(conn, "lab")
for i in range(3):
    devices.register_device(conn, f"d{i}", "lab", "1.0.0")
rid = rollouts.create_rollout(conn, "2.0.0", ["lab"], 50)
print(rollouts.advance(conn, rid), rollouts.get_rollout(conn, rid))
