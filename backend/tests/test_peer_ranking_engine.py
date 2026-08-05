"""Tests for the peer ranking engine."""

from __future__ import annotations

import pytest

from backend.app.analytics.peer_ranking_engine import (
    _build_deterministic_rankings,
    _extract_post_metrics,
    _follower_band_label,
    _validate_ranking_response,
    build_creator_rankings,
)
from backend.app.domain.account_models import (
    CreatorPeerRankings,
    PeerRankingMetric,
)


class _FakeCore:
    def __init__(self, reach, impressions, likes, comments, shares, saves):
        self.reach = reach
        self.impressions = impressions
        self.likes = likes
        self.comments = comments
        self.shares = shares
        self.saves = saves


class _FakeAudience:
    def __init__(self, s4):
        self.s4_raw_0_100 = s4


class _FakePost:
    def __init__(self, reach, impressions, likes, comments, shares, saves, s4):
        self.core_metrics = _FakeCore(reach, impressions, likes, comments, shares, saves)
        self.audience_relevance_score = _FakeAudience(s4)


class _FakeDerived:
    def __init__(self, engagement_rate):
        self.engagement_rate = engagement_rate


def _make_post(reach=1000.0, impressions=1500.0, likes=50, comments=5,
               shares=10, saves=15, s4=65.0):
    return _FakePost(reach, impressions, likes, comments, shares, saves, s4)


class TestFollowerBandLabel:
    def test_small_band(self):
        assert _follower_band_label(2000) == "0-10k"

    def test_medium_band(self):
        assert _follower_band_label(20000) == "10k-100k"

    def test_large_band(self):
        assert _follower_band_label(300000) == "100k-1M"

    def test_very_large_band(self):
        assert _follower_band_label(600000) == "100k-1M"

    def test_million_plus_band(self):
        assert _follower_band_label(2_000_000) == "1M+"

    def test_none_follower_count(self):
        assert "Unknown" in _follower_band_label(None)


class TestExtractPostMetrics:
    def test_empty_posts_returns_zeros(self):
        result = _extract_post_metrics([])
        assert result == {
            "avg_reach": 0.0, "avg_er": 0.0, "avg_impressions": 0.0,
            "avg_save_rate": 0.0, "avg_s4": 0.0,
        }

    def test_single_post_extracts_correctly(self):
        post = _make_post(reach=2000, impressions=2500, likes=80, comments=10,
                          shares=20, saves=30, s4=70)
        result = _extract_post_metrics([post])
        assert result["avg_reach"] == pytest.approx(2000)
        assert result["avg_er"] == pytest.approx(7.0)
        assert result["avg_impressions"] == pytest.approx(2500)
        assert result["avg_save_rate"] == pytest.approx(1.5)
        assert result["avg_s4"] == pytest.approx(70)

    def test_multiple_posts_averages(self):
        posts = [
            _make_post(reach=1000, impressions=1500, likes=50, comments=5, shares=10, saves=15, s4=60),
            _make_post(reach=2000, impressions=2500, likes=80, comments=10, shares=20, saves=30, s4=70),
        ]
        result = _extract_post_metrics(posts)
        assert result["avg_reach"] == pytest.approx(1500)
        assert result["avg_s4"] == pytest.approx(65)

    def test_decimal_engagement_rate_is_converted_to_percent(self):
        post = _make_post()
        post.derived_metrics = _FakeDerived(0.035)

        assert _extract_post_metrics([post])["avg_er"] == pytest.approx(3.5)

    def test_percentage_like_engagement_rate_is_not_rescaled(self):
        post = _make_post()
        post.derived_metrics = _FakeDerived(0.75)

        assert _extract_post_metrics([post])["avg_er"] == pytest.approx(0.75)


class TestDeterministicRankings:
    def test_produces_valid_structure(self):
        metrics = {
            "avg_reach": 3000, "avg_er": 4.0, "avg_impressions": 4000,
            "avg_save_rate": 1.5, "avg_s4": 60,
        }
        result = _build_deterministic_rankings(metrics, 20000)
        assert isinstance(result, dict)
        assert len(result["rankings"]) == 5
        assert all("metric_key" in r for r in result["rankings"])
        assert all("percentile" in r for r in result["rankings"])
        assert all(0 <= r["percentile"] <= 100 for r in result["rankings"])
        assert len(result["rankings"][0]["thresholds"]) == 4
        assert "audience_score" in result
        assert result["fallback_used"] is True
        assert "best_stat_key" in result
        assert "comparison_context" in result

    def test_fallback_used_flag_is_true(self):
        metrics = {
            "avg_reach": 0, "avg_er": 0, "avg_impressions": 0,
            "avg_save_rate": 0, "avg_s4": 50,
        }
        result = _build_deterministic_rankings(metrics, None)
        assert result["fallback_used"] is True

    def test_metrics_with_zero_values_still_produce_results(self):
        metrics = {
            "avg_reach": 0, "avg_er": 0, "avg_impressions": 0,
            "avg_save_rate": 0, "avg_s4": 0,
        }
        result = _build_deterministic_rankings(metrics, 1000)
        assert len(result["rankings"]) == 5
        assert all(0 <= r["percentile"] <= 100 for r in result["rankings"])

    def test_follower_band_changes_reach_benchmark(self):
        metrics = {"avg_reach": 30_000, "avg_er": 3.5, "avg_impressions": 40_000, "avg_save_rate": 1.2, "avg_s4": 50}

        nano = _build_deterministic_rankings(metrics, 5_000)
        mega = _build_deterministic_rankings(metrics, 1_000_000)

        assert nano["rankings"][0]["cohort_average"] < mega["rankings"][0]["cohort_average"]


class TestValidateRankingResponse:
    def test_valid_payload_passes(self):
        payload = {
            "rankings": [
                {
                    "metric_key": "reach", "metric_label": "Reach",
                    "creator_value": 1000, "percentile": 75.0,
                    "tier_label": "Top 25%", "cohort_average": 500,
                    "thresholds": [],
                },
            ],
            "audience_score": {
                "score": 60, "percentile": 55.0, "tier_label": "Top 25%",
                "cohort_average": 50, "thresholds": [],
            },
            "best_stat_key": "reach",
            "comparison_context": "Test",
        }
        assert _validate_ranking_response(payload) is True

    def test_missing_rankings_fails(self):
        assert _validate_ranking_response({}) is False

    def test_missing_percentile_in_ranking_fails(self):
        payload = {
            "rankings": [{"metric_key": "reach"}],
            "audience_score": {"percentile": 50},
        }
        assert _validate_ranking_response(payload) is False

    def test_percentile_out_of_range_fails(self):
        payload = {
            "rankings": [{"metric_key": "reach", "percentile": 150.0}],
            "audience_score": {"percentile": 50},
        }
        assert _validate_ranking_response(payload) is False


class TestBuildCreatorRankings:
    def test_returns_valid_fallback_when_no_llm(self, monkeypatch):
        monkeypatch.setenv("AI_PEER_RANKINGS_ENABLED", "0")
        posts = [_make_post()]
        result = build_creator_rankings(posts=posts, follower_count=20000)
        assert result["fallback_used"] is True
        assert len(result["rankings"]) == 5

    def test_can_validate_as_pydantic_model(self):
        posts = [_make_post()]
        result = build_creator_rankings(posts=posts, follower_count=20000)
        model = CreatorPeerRankings(**result)
        assert model.fallback_used is True
        assert len(model.rankings) == 5
        assert isinstance(model.rankings[0], PeerRankingMetric)
        assert 0 <= model.rankings[0].percentile <= 100
        assert model.audience_score.score >= 0
        assert model.best_stat_key != ""
