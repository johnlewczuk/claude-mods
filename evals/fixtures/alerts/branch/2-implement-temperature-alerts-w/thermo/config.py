import json

DEFAULTS = {
    "poll_interval_s": 10,
    "alert_threshold_c": 80,
    "alert_webhook_url": None,
    "alert_severity_levels": ["warn", "crit"],
}


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    return {**DEFAULTS, **cfg}
