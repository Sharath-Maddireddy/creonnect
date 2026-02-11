"""
Service layer tests for snapshot and script generation.
"""

import pytest

from backend.app.services.snapshot_service import build_creator_snapshot_service
from backend.app.services.script_service import generate_creator_script_service


def test_snapshot_service_returns_snapshot():
    result = build_creator_snapshot_service("demo")
    assert isinstance(result, dict)
    assert result.get("creator_id") is not None
    assert "engagement_rate_by_views" in result


def test_snapshot_service_invalid_creator():
    with pytest.raises(ValueError):
        build_creator_snapshot_service("does_not_exist")


def test_script_service_returns_script():
    result = generate_creator_script_service("demo")
    assert isinstance(result, dict)
    assert result.get("hook")
    assert result.get("body")
    assert result.get("cta")


def test_script_service_invalid_creator():
    with pytest.raises(ValueError):
        generate_creator_script_service("does_not_exist")


