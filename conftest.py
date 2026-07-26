"""Pytest bootstrap for repository-local imports."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).resolve().parent
root_str = str(ROOT)
if root_str not in sys.path:
    sys.path.insert(0, root_str)


@pytest.fixture
def fake_redis_client():
    """Shared fakeredis client fixture for tests that patch Redis calls."""
    fakeredis = pytest.importorskip("fakeredis")
    return fakeredis.FakeRedis(decode_responses=True)


def make_fake_redis_client():
    import fakeredis
    return fakeredis.FakeRedis(decode_responses=True)

