"""Small shared helpers."""
import re
import time
from datetime import datetime, timedelta, timezone

_DURATION = re.compile(r"^(\d+)([smhd])$")
_UNITS = {"s": 1, "m": 60, "h": 3600, "d": 86400}


def utcnow():
    """Timezone-aware current time in UTC. Use this, not datetime.now()."""
    return datetime.now(timezone.utc)


def parse_duration(text):
    """'90s', '5m', '2h', '1d' -> timedelta. Raises ValueError otherwise."""
    m = _DURATION.match(text.strip())
    if not m:
        raise ValueError(f"bad duration: {text!r}")
    return timedelta(seconds=int(m.group(1)) * _UNITS[m.group(2)])


def chunked(items, size):
    """Split a list into consecutive lists of at most `size` items."""
    if size < 1:
        raise ValueError("size must be >= 1")
    return [items[i:i + size] for i in range(0, len(items), size)]


def retry(fn, attempts=3, backoff_s=0.5, retry_on=(OSError,)):
    """Call fn(); on an exception in retry_on, wait and try again."""
    for i in range(attempts):
        try:
            return fn()
        except retry_on:
            if i == attempts - 1:
                raise
            time.sleep(backoff_s * (2 ** i))
