"""Service configuration: defaults merged with an optional JSON file."""
import json

DEFAULTS = {
    "db_path": "fleet.db",
    "http_port": 8080,
    "rollout_failure_threshold": 0.2,
    "rollout_webhook_url": None,
    "rollout_resume_after": "30m",
}


def load_config(path=None):
    cfg = dict(DEFAULTS)
    if path:
        with open(path) as f:
            cfg.update(json.load(f))
    return cfg
