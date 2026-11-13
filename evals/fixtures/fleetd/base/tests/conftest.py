import os
import sys

import pytest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)

from fleet import db  # noqa: E402


@pytest.fixture
def conn():
    c = db.connect(":memory:")
    db.migrate(c, os.path.join(ROOT, "migrations"))
    yield c
    c.close()
