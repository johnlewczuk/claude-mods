"""HTTP handlers for rollouts."""
from . import rollouts
from .http import error_response, json_response
from .util import utcnow


def _errors(fn):
    """Map domain errors to the shared error shape."""
    def wrapper(*args, **kwargs):
        try:
            return fn(*args, **kwargs)
        except KeyError as e:
            return error_response(404, f"not found: {e}")
        except ValueError as e:
            return error_response(400, str(e))
    return wrapper


@_errors
def handle_create(conn, req):
    rollout_id = rollouts.create_rollout(
        conn, req.body["firmware"], req.body["groups"], int(req.body.get("batch_percent", 10))
    )
    return json_response({"id": rollout_id}, 202)


@_errors
def handle_list(conn, req):
    status = req.query.get("status")
    if status is not None and status not in rollouts.STATUSES:
        raise ValueError(f"unknown status: {status}")
    return json_response({"rollouts": rollouts.list_rollouts(conn, status)})


@_errors
def handle_get(conn, req, rollout_id):
    rollout = rollouts.get_rollout(conn, rollout_id)
    if rollout is None:
        raise KeyError(rollout_id)
    rollout["failure_rate"] = rollouts.failure_rate(conn, rollout_id)
    return json_response(rollout)


@_errors
def handle_result(conn, req, rollout_id, cfg):
    recorded = rollouts.record_result(
        conn, rollout_id, req.body["device_id"], req.body["result"], cfg
    )
    return json_response({"recorded": recorded})


def handle_tick(conn, req, cfg):
    """Called by the scheduler every minute."""
    return json_response({"resumed": rollouts.resume_due(conn, utcnow(), cfg)})
