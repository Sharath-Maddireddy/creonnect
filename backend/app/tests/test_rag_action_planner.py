"""Unit tests for the RAG action plan generator."""

from __future__ import annotations

from backend.app.ai.rag import generate_action_plan, _build_planner_context


SAMPLE_METRICS = {
    "followers": 120000,
    "growth_score": 65,
    "avg_views": 45000,
    "avg_engagement_rate_by_views": 0.042,
    "posts_per_week": 4.5,
}
SAMPLE_NICHE = {"primary_niche": "fitness"}
SAMPLE_MOMENTUM = {"momentum_label": "accelerating", "momentum_value": 85}
SAMPLE_BEST_TIME = {"best_posting_hours": [18, 20, 21]}


def test_build_planner_context_extracts_fields():
    ctx = _build_planner_context(
        SAMPLE_METRICS, SAMPLE_NICHE, SAMPLE_MOMENTUM, SAMPLE_BEST_TIME, []
    )
    assert ctx["primary_niche"] == "fitness"
    assert ctx["followers"] == 120000
    assert ctx["momentum_label"] == "accelerating"
    assert ctx["best_posting_hours"] == [18, 20, 21]


def test_generate_action_plan_llm_success(monkeypatch):
    """LLM returns valid JSON -> should be used as-is."""
    fake_response = (
        '{"diagnosis": "test diag", '
        '"weekly_plan": ["a", "b", "c"], '
        '"content_suggestions": ["x", "y"], '
        '"posting_schedule": ["p1", "p2", "p3"], '
        '"cta_tips": ["t1", "t2"]}'
    )
    monkeypatch.setattr(
        "backend.app.ai.llm_client.LLMClient.generate",
        lambda *a, **kw: fake_response,
    )
    result = generate_action_plan(
        SAMPLE_METRICS, SAMPLE_NICHE, SAMPLE_MOMENTUM, SAMPLE_BEST_TIME, []
    )
    assert result["diagnosis"] == "test diag"
    assert len(result["weekly_plan"]) == 3
    assert len(result["content_suggestions"]) == 2


def test_generate_action_plan_falls_back_on_llm_error(monkeypatch):
    """LLM raises -> falls back to deterministic output."""
    monkeypatch.setattr(
        "backend.app.ai.llm_client.LLMClient.generate",
        lambda *a, **kw: (_ for _ in ()).throw(RuntimeError("LLM down")),
    )
    result = generate_action_plan(
        SAMPLE_METRICS, SAMPLE_NICHE, SAMPLE_MOMENTUM, SAMPLE_BEST_TIME, []
    )
    assert {"diagnosis", "weekly_plan", "content_suggestions", "posting_schedule", "cta_tips"}.issubset(result.keys())
    assert isinstance(result["diagnosis"], str)
    assert len(result["weekly_plan"]) > 0


def test_generate_action_plan_uses_knowledge_chunks(monkeypatch):
    """knowledge_chunks should be injected into the LLM prompt."""
    prompts_seen = []

    def fake_generate(self, messages):
        prompts_seen.append(messages.get("user", ""))
        return (
            '{"diagnosis": "d", "weekly_plan": ["a","b","c"], '
            '"content_suggestions": ["x","y"], '
            '"posting_schedule": ["p","q","r"], "cta_tips": ["t1","t2"]}'
        )

    monkeypatch.setattr("backend.app.ai.llm_client.LLMClient.generate", fake_generate)
    generate_action_plan(
        SAMPLE_METRICS,
        SAMPLE_NICHE,
        SAMPLE_MOMENTUM,
        SAMPLE_BEST_TIME,
        [],
        knowledge_chunks=["chunk about fitness growth hacks"],
    )
    assert "chunk about fitness growth hacks" in prompts_seen[0]
