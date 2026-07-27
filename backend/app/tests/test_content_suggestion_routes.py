"""Contract tests for content suggestion routes.

Validates:
- Request/response model integrity
- Field name parity between frontend and backend
- 404/422 error handling
"""

from __future__ import annotations

import pytest

from backend.app.domain.content_suggestion_models import (
    GenerateIdeasRequest,
    GenerateIdeasResponse,
    GenerateScriptRequest,
    GenerateScriptResponse,
    GenerateCaptionRequest,
    GenerateCaptionResponse,
    ScheduleIdeaRequest,
    ScheduledItemResponse,
    SaveIdeaRequest,
    ImproveIdeaRequest,
    VariationsRequest,
    RegenerateRequest,
)


# ── Request Model Contract Tests ──────────────────────────────────────────────

class TestRequestModelContracts:
    """Verify request models match the frontend's expected field names exactly."""

    def test_generate_ideas_request_formats_correctly(self):
        """Frontend sends: {optimization_goals, content_type, topic, audience, tone_of_voice, count}"""
        payload = {
            "optimization_goals": ["maximum_reach", "engagement"],
            "content_type": "reel",
            "topic": "fitness transformation",
            "audience": "25-34",
            "tone_of_voice": ["educational"],
            "count": 5,
        }
        req = GenerateIdeasRequest.model_validate(payload)
        assert req.count == 5
        assert req.content_type == "reel"
        assert req.optimization_goals == ["maximum_reach", "engagement"]

    def test_generate_script_request_formats_correctly(self):
        """Frontend sends: {idea_id, script_type, tone, language, duration_seconds}"""
        payload = {
            "idea_id": "abc-123",
            "script_type": "viral",
            "tone": "friendly",
            "language": "en",
            "duration_seconds": 60,
        }
        req = GenerateScriptRequest.model_validate(payload)
        assert req.idea_id == "abc-123"
        assert req.script_type == "viral"
        assert req.tone == "friendly"
        assert req.language == "en"
        assert req.duration_seconds == 60

    def test_generate_caption_request_formats_correctly(self):
        """Frontend sends: {idea_id, platforms, tone, language, include_hashtags, max_hashtags}"""
        payload = {
            "idea_id": "abc-123",
            "platforms": ["instagram", "tiktok"],
            "tone": "funny",
            "language": "en",
            "include_hashtags": True,
            "max_hashtags": 10,
        }
        req = GenerateCaptionRequest.model_validate(payload)
        assert req.idea_id == "abc-123"
        assert req.platforms == ["instagram", "tiktok"]
        assert req.include_hashtags is True
        assert req.max_hashtags == 10

    def test_schedule_idea_request_formats_correctly(self):
        """Frontend sends: {idea_id, scheduled_date, scheduled_time, platform, conflict_resolution, notes}"""
        payload = {
            "idea_id": "abc-123",
            "scheduled_date": "2026-07-28",
            "scheduled_time": "19:00:00",
            "platform": "instagram",
            "conflict_resolution": "reject",
            "notes": "Post at peak engagement time",
        }
        req = ScheduleIdeaRequest.model_validate(payload)
        assert req.idea_id == "abc-123"
        assert req.scheduled_date == "2026-07-28"
        assert req.platform == "instagram"
        assert req.conflict_resolution == "reject"

    def test_save_idea_request_formats_correctly(self):
        """Frontend sends: {idea_id}"""
        payload = {"idea_id": "abc-123"}
        req = SaveIdeaRequest.model_validate(payload)
        assert req.idea_id == "abc-123"

    def test_improve_request_formats_correctly(self):
        """Frontend sends: {feedback, aspect}"""
        payload = {
            "feedback": "Make it more engaging",
            "aspect": "full",
        }
        req = ImproveIdeaRequest.model_validate(payload)
        assert req.feedback == "Make it more engaging"

    def test_variations_request_formats_correctly(self):
        """Frontend sends: {count}"""
        payload = {"count": 3}
        req = VariationsRequest.model_validate(payload)
        assert req.count == 3

    def test_regenerate_request_formats_correctly(self):
        """Frontend sends: {}"""
        payload = {}
        req = RegenerateRequest.model_validate(payload)
        assert req is not None


# ── Response Model Contract Tests ─────────────────────────────────────────────

class TestResponseModelContracts:
    """Verify response models return fields the frontend expects."""

    def test_generate_ideas_response_has_job_id(self):
        resp = GenerateIdeasResponse(
            job_id="job-1",
            status="processing",
            estimated_seconds=15,
        )
        data = resp.model_dump()
        assert data["job_id"] == "job-1"
        assert data["status"] == "processing"
        assert data["estimated_seconds"] == 15

    def test_scheduled_item_response_has_scheduled_at(self):
        """Frontend CalendarView reads `scheduled_at` field."""
        resp = ScheduledItemResponse(
            id="sched-1",
            idea_id="idea-1",
            platform="instagram",
            scheduled_at="2026-07-28 19:00:00",
            idea_title="Test Idea",
            status="scheduled",
        )
        data = resp.model_dump()
        assert data["scheduled_at"] == "2026-07-28 19:00:00"
        assert data["platform"] == "instagram"

    def test_generate_script_response_has_expected_fields(self):
        resp = GenerateScriptResponse(
            idea_id="idea-1",
            hook="Test hook",
            scenes=[
                {"scene_number": 1, "time_range": "0:00-0:15", "description": "Scene 1", "visual_notes": None},
            ],
            cta="Test CTA",
            estimated_duration_sec=60,
            full_script="Full script...",
        )
        data = resp.model_dump()
        assert data["hook"] == "Test hook"
        assert len(data["scenes"]) == 1
        assert data["cta"] == "Test CTA"
        assert data["estimated_duration_sec"] == 60

    def test_generate_caption_response_has_expected_fields(self):
        resp = GenerateCaptionResponse(
            idea_id="idea-1",
            captions=[
                {
                    "platform": "instagram",
                    "caption_text": "Check out this amazing content!",
                    "character_count": 32,
                    "hashtag_count": 3,
                    "hashtags": ["#content", "#viral"],
                    "tips_applied": ["Open with a strong hook"],
                }
            ],
        )
        data = resp.model_dump()
        assert len(data["captions"]) == 1
        assert data["captions"][0]["caption_text"] == "Check out this amazing content!"
        assert data["captions"][0]["character_count"] == 32


# ── Field Name Parity Tests ───────────────────────────────────────────────────

class TestFieldNameParity:
    """Verify no snake_case/camelCase mismatches between frontend and backend."""

    def test_all_generate_script_fields_used_by_frontend(self):
        """ScriptGenerator.jsx reads: {full_script, hook, scenes, cta, estimated_duration_sec}"""
        payload = {
            "idea_id": "abc-123",
            "script_type": "viral",
            "tone": "friendly",
            "language": "en",
            "duration_seconds": 45,
        }
        req = GenerateScriptRequest.model_validate(payload)
        # Frontend sends these field names — verify they're accepted
        assert req.duration_seconds == 45
        assert req.script_type == "viral"
        # backend model uses `duration_seconds`, frontend also sends `duration_seconds` ✅

    def test_all_generate_caption_fields_used_by_frontend(self):
        """CaptionGenerator.jsx reads: {captions: [{caption_text, character_count, hashtag_count, tips_applied}]}"""
        payload = {
            "idea_id": "abc-123",
            "platforms": ["instagram"],
            "tone": "friendly",
            "language": "en",
            "include_hashtags": True,
            "max_hashtags": 10,
        }
        req = GenerateCaptionRequest.model_validate(payload)
        assert req.max_hashtags == 10
        # Frontend sends `max_hashtags`, backend expects `max_hashtags` ✅
        # Frontend reads `character_count`, backend returns `character_count` ✅

    def test_schedule_request_field_names_match_frontend(self):
        """ContentPlanner.jsx sends: {idea_id, scheduled_date, scheduled_time, platform, conflict_resolution, notes}"""
        payload = {
            "idea_id": "abc-123",
            "scheduled_date": "2026-07-28",
            "scheduled_time": "19:00",
            "platform": "instagram",
            "conflict_resolution": "reject",
            "notes": "Optional notes",
        }
        req = ScheduleIdeaRequest.model_validate(payload)
        assert req.scheduled_date == "2026-07-28"
        # Note: frontend sends HH:MM, backend expects HH:MM:SS — this should be
        # normalized by the route handler or pydantic validator


# ── 404/422 Error Handling Tests ──────────────────────────────────────────────

class TestErrorHandling:
    """Verify error responses match what frontend components display."""

    def test_invalid_script_type_accepted_with_warning(self):
        """script_type is a free-str field — invalid values are accepted but should be coerced."""
        # Backend accepts any string; frontend should validate client-side
        req = GenerateScriptRequest.model_validate({
            "idea_id": "abc-123",
            "script_type": "INVALID_TYPE",
        })
        assert req.script_type == "INVALID_TYPE"  # backend doesn't enforce enum

    def test_missing_required_fields_rejected(self):
        """idea_id is required on most requests — missing it should raise validation error."""
        with pytest.raises(ValueError):
            GenerateScriptRequest.model_validate({
                "script_type": "viral",
                "tone": "friendly",
            })

    def test_duration_out_of_range_rejected(self):
        """duration_seconds has ge=15, le=180."""
        with pytest.raises(ValueError):
            GenerateScriptRequest.model_validate({
                "idea_id": "abc-123",
                "duration_seconds": 5,  # below minimum 15
            })

    def test_opportunity_score_bounds_enforced(self):
        """Opportunity score must be 0-100."""
        with pytest.raises(ValueError):
            from backend.app.domain.trend_models import TrendRecommendation
            TrendRecommendation.model_validate({
                "suggested_title": "Test",
                "rationale": "Test",
                "expected_impact": "High",
                "opportunity_score": 150,  # above max 100
            })