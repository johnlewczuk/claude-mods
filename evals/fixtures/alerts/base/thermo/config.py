import json

DEFAULTS = {"poll_interval_s": 10}


def load_config(path):
    with open(path) as f:
        cfg = json.load(f)
    return {**DEFAULTS, **cfg}
