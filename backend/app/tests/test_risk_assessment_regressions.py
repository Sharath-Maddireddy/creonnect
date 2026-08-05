from __future__ import annotations

from datetime import date, datetime, timezone
from types import SimpleNamespace

from backend.app.services.risk_assessment import _assess_save_rate_risks, _published_sort_key


def test_publish_sort_key_accepts_dates_and_datetimes() -> None:
    date_post = SimpleNamespace(published_at=date(2025, 1, 1))
    datetime_post = SimpleNamespace(published_at=datetime(2025, 1, 2, tzinfo=timezone.utc))

    assert _published_sort_key(datetime_post) > _published_sort_key(date_post)


def test_low_save_rate_uses_reach_not_likes() -> None:
    posts = [
        SimpleNamespace(core_metrics=SimpleNamespace(reach=1_000, likes=10_000, saves=40))
        for _ in range(10)
    ]

    assert _assess_save_rate_risks(posts) == []
