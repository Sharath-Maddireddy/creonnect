"""Unit tests for shared utility functions introduced during the refactor.

Covers:
- number_utils: safe_float, safe_float_or, now_iso
- RedisJobStore: base_status schema, update merge, write/get round-trip (mocked)
- ai_analysis_service._resolve_score
- ai_analysis_service._clamp_vq
"""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

import pytest

from backend.app.utils.number_utils import now_iso, safe_float, safe_float_or


# ---------------------------------------------------------------------------
# safe_float
# ---------------------------------------------------------------------------

class TestSafeFloat:
    def test_none_returns_none(self):
        assert safe_float(None) is None

    def test_valid_int(self):
        assert safe_float(42) == 42.0

    def test_valid_float(self):
        assert safe_float(3.14) == pytest.approx(3.14)

    def test_valid_numeric_string(self):
        assert safe_float("2.5") == pytest.approx(2.5)

    def test_non_numeric_string_returns_none(self):
        assert safe_float("abc") is None

    def test_bool_true_returns_float(self):
        # bool is a subclass of int in Python; safe_float does NOT special-case bool
        assert safe_float(True) == 1.0

    def test_empty_string_returns_none(self):
        assert safe_float("") is None

    def test_list_returns_none(self):
        assert safe_float([1, 2]) is None


# ---------------------------------------------------------------------------
# safe_float_or
# ---------------------------------------------------------------------------

class TestSafeFloatOr:
    def test_none_returns_default(self):
        assert safe_float_or(None) == 0.0

    def test_none_custom_default(self):
        assert safe_float_or(None, default=99.0) == pytest.approx(99.0)

    def test_valid_value(self):
        assert safe_float_or("7.5", default=0.0) == pytest.approx(7.5)

    def test_invalid_string_returns_default(self):
        assert safe_float_or("bad", default=5.0) == pytest.approx(5.0)

    def test_zero_is_not_default(self):
        # 0.0 is a valid float; should NOT fall back to default
        assert safe_float_or(0.0, default=1.0) == pytest.approx(0.0)


# ---------------------------------------------------------------------------
# now_iso
# ---------------------------------------------------------------------------

class TestNowIso:
    def test_returns_string(self):
        result = now_iso()
        assert isinstance(result, str)

    def test_parseable_as_datetime(self):
        result = now_iso()
        parsed = datetime.fromisoformat(result)
        assert parsed.tzinfo is not None

    def test_utc_timezone(self):
        result = now_iso()
        parsed = datetime.fromisoformat(result)
        assert parsed.utcoffset().total_seconds() == 0


# ---------------------------------------------------------------------------
# RedisJobStore (unit — Redis calls mocked)
# ---------------------------------------------------------------------------

class TestRedisJobStore:
    def _make_store(self):
        from backend.app.infra.redis_job_store import RedisJobStore
        return RedisJobStore(key_prefix="test:job:", ttl_seconds=3600)

    def test_base_status_schema(self):
        store = self._make_store()
        status = store.base_status("abc123")
        assert status["job_id"] == "abc123"
        assert status["status"] == "queued"
        assert status["result"] is None
        assert status["error"] is None
        assert "created_at" in status

    def test_base_status_extra_fields(self):
        store = self._make_store()
        extra = {"progress": None, "warnings": [], "quality": None}
        status = store.base_status("x", extra)
        assert "progress" in status
        assert status["warnings"] == []

    def test_update_merges_fields(self):
        store = self._make_store()
        with patch("backend.app.infra.redis_job_store.set_json") as mock_set, \
             patch("backend.app.infra.redis_job_store.get_json", return_value=None):
            result = store.update("abc", status="started", started_at="2024-01-01T00:00:00+00:00")
            assert result["status"] == "started"
            assert result["started_at"] == "2024-01-01T00:00:00+00:00"
            mock_set.assert_called_once()

    def test_key_uses_prefix(self):
        store = self._make_store()
        assert store._key("myjob") == "test:job:myjob"

    def test_get_returns_none_when_missing(self):
        store = self._make_store()
        with patch("backend.app.infra.redis_job_store.get_json", return_value=None):
            assert store.get("nonexistent") is None


# ---------------------------------------------------------------------------
# _resolve_score (ai_analysis_service)
# ---------------------------------------------------------------------------

class TestResolveScore:
    def test_correct_instance_returned_as_is(self):
        from backend.app.services.ai_analysis_service import _resolve_score
        from backend.app.domain.post_models import VisualQualityScore
        obj = VisualQualityScore()
        assert _resolve_score(obj, VisualQualityScore) is obj

    def test_wrong_type_returns_default(self):
        from backend.app.services.ai_analysis_service import _resolve_score
        from backend.app.domain.post_models import VisualQualityScore
        result = _resolve_score({"total": 5}, VisualQualityScore)
        assert isinstance(result, VisualQualityScore)

    def test_none_returns_default(self):
        from backend.app.services.ai_analysis_service import _resolve_score
        from backend.app.domain.post_models import ContentClarityScore
        result = _resolve_score(None, ContentClarityScore)
        assert isinstance(result, ContentClarityScore)


# ---------------------------------------------------------------------------
# _clamp_vq (ai_analysis_service)
# ---------------------------------------------------------------------------

class TestClampVq:
    def _fn(self):
        from backend.app.services.ai_analysis_service import _clamp_vq
        return _clamp_vq

    def test_scalar_broadcast(self):
        result = self._fn()(8.0)
        assert result is not None
        assert all(v == pytest.approx(8.0) for v in result.values())

    def test_scalar_clamped_above_10(self):
        result = self._fn()(999)
        assert all(v == pytest.approx(10.0) for v in result.values())

    def test_scalar_clamped_below_0(self):
        result = self._fn()(-5)
        assert all(v == pytest.approx(0.0) for v in result.values())

    def test_dict_input_clamped(self):
        raw = {"composition": 12.0, "lighting": -1.0, "subject_clarity": 5.0, "aesthetic_quality": 7.5}
        result = self._fn()(raw)
        assert result is not None
        assert result["composition"] == pytest.approx(10.0)
        assert result["lighting"] == pytest.approx(0.0)
        assert result["subject_clarity"] == pytest.approx(5.0)

    def test_none_returns_none(self):
        assert self._fn()(None) is None

    def test_incomplete_dict_returns_none(self):
        assert self._fn()({"composition": 5.0}) is None