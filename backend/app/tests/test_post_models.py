from __future__ import annotations

import pytest
from pydantic import ValidationError

from backend.app.domain.post_models import CoreMetrics, DerivedMetrics


def test_core_metrics_reject_negative_counts() -> None:
    with pytest.raises(ValidationError):
        CoreMetrics(reach=-1)


def test_derived_metrics_reject_negative_rates_and_totals() -> None:
    with pytest.raises(ValidationError):
        DerivedMetrics(engagement_rate=-0.1)

    with pytest.raises(ValidationError):
        DerivedMetrics(engagements_total=-1)


def test_optional_core_and_derived_metric_fields_still_allow_none() -> None:
    metrics = CoreMetrics(reach=None, likes=None)
    derived = DerivedMetrics(engagement_rate=None, engagements_total=None)

    assert metrics.reach is None
    assert metrics.likes is None
    assert derived.engagement_rate is None
    assert derived.engagements_total is None
