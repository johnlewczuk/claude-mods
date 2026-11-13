from datetime import timedelta

import pytest

from fleet.util import chunked, parse_duration


def test_parse_duration():
    assert parse_duration("90s") == timedelta(seconds=90)
    assert parse_duration("2h") == timedelta(hours=2)
    with pytest.raises(ValueError):
        parse_duration("5 minutes")


def test_chunked():
    assert chunked([1, 2, 3, 4, 5], 2) == [[1, 2], [3, 4], [5]]
