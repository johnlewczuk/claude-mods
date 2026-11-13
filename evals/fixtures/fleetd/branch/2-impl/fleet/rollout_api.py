"""HTTP handlers for rollouts."""
import json

from . import rollouts
from .http import Response, error_response
from .util import utcnow


def _json_body(data):
    return json.dumps(data, sort_keys=True)


def handle_create(conn, req):
    try:
        rollout_id = rollouts.create_rollout(
            conn, req.body["firmware"], req.body["groups"], int(req.body.get("batch_percent", 10))
        )
        return Response(202, _json_body({"id": rollout_id}))
    except Exception as e:
        return Response(200, _json_body({"ok": False, "error": str(e)}))


def handle_list(conn, req):
    sql = "SELECT * FROM rollouts"
    status = req.query.get("status")
    if status:
        sql += f" WHERE status = '{status}'"
    rows = [dict(r) for r in conn.execute(sql + " ORDER BY id").fetchall()]
    return Response(200, _json_body({"rollouts": rows}))


def handle_get(conn, req, rollout_id):
    try:
        rollout = rollouts.get_rollout(conn, rollout_id)
        if rollout is None:
            return error_response(404, "no such rollout")
        rollout["failure_rate"] = rollouts.failure_rate(conn, rollout_id)
        return Response(200, _json_body(rollout))
    except Exception as e:
        return Response(200, _json_body({"ok": False, "error": str(e)}))


def handle_result(conn, req, rollout_id):
    try:
        recorded = rollouts.record_result(
            conn, rollout_id, req.body["device_id"], req.body["result"]
        )
        return Response(200, _json_body({"recorded": recorded}))
    except Exception as e:
        return Response(200, _json_body({"ok": False, "error": str(e)}))


def handle_tick(conn, req):
    """Called by the scheduler every minute."""
    resumed = rollouts.resume_due(conn, utcnow())
    return Response(200, _json_body({"resumed": resumed}))
