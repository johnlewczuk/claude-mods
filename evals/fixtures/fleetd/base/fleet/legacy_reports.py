"""Old CSV report export. Scheduled for replacement; do not extend."""
import csv
import io


def firmware_report(conn, firmware_prefix):
    rows = conn.execute(
        "SELECT id, group_name, firmware FROM devices WHERE firmware LIKE '"
        + firmware_prefix
        + "%' ORDER BY id"
    ).fetchall()
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["id", "group", "firmware"])
    for r in rows:
        w.writerow(list(r))
    return out.getvalue()
