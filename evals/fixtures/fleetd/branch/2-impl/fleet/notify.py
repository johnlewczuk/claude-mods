"""Webhook notifications for rollout events."""
import urllib.request

from .util import retry


def notify_paused(url, rollout, failure_rate):
    if not url:
        return None
    from .rollout_api import _json_body  # imported here to avoid a circular import

    body = _json_body(
        {"event": "rollout_paused", "rollout_id": rollout["id"], "failure_rate": failure_rate}
    )

    def send():
        resp = urllib.request.urlopen(
            urllib.request.Request(
                url, data=body.encode(), headers={"Content-Type": "application/json"}
            ),
            timeout=5,
        )
        return resp.status

    return retry(send, attempts=5, retry_on=(Exception,))
