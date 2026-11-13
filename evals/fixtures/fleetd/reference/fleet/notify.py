"""Webhook notifications for rollout events."""
import json
import urllib.error
import urllib.request

from .util import retry


def _transient(exc):
    return not isinstance(exc, urllib.error.HTTPError) or exc.code >= 500


def notify_paused(url, rollout, failure_rate):
    if not url:
        return None
    body = json.dumps(
        {"event": "rollout_paused", "rollout_id": rollout["id"], "failure_rate": failure_rate}
    ).encode()

    def send():
        req = urllib.request.Request(url, data=body, headers={"Content-Type": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=5) as resp:
                return resp.status
        except urllib.error.HTTPError as e:
            if not _transient(e):
                raise ValueError(f"webhook rejected: {e.code}") from e
            raise

    return retry(send, attempts=3, retry_on=(OSError,))
