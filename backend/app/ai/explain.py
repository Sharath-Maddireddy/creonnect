from typing import List, Dict, Union

from backend.app.ai.context import build_creator_context
from backend.app.ai.prompt_builder import build_creator_explanation_prompt
from backend.app.ai.llm_client import LLMClient, LLMClientError
from backend.app.ai.schemas import CreatorProfileAIInput, CreatorPostAIInput
from backend.app.utils.logger import logger


class CreatorExplanationService:
    """
    Orchestrates:
    deterministic AI outputs -> RAG context -> prompt -> LLM explanation
    Includes deterministic fallback if LLM fails.
    """

    def __init__(self, model_name: str = "gpt-4o-mini"):
        self.llm = LLMClient(model_name=model_name)

    def explain_creator(
        self,
        profile: CreatorProfileAIInput,
        posts: List[CreatorPostAIInput],
        ai_outputs: Dict
    ) -> Union[str, Dict]:
        """
        Generate creator explanation.
        Returns LLM response on success, or structured fallback on failure.
        """
        context = build_creator_context(profile, posts, ai_outputs)
        prompt = build_creator_explanation_prompt(context)

        try:
            return self.llm.generate(prompt)
        except (LLMClientError, Exception) as e:
            logger.error(f"[Explain] LLM failed, returning deterministic fallback: {e}")
            # Return structured fallback - never crash
            return {
                "status": "partial",
                "message": "AI explanation temporarily unavailable",
                "growth": ai_outputs.get("growth", {}),
                "posts": ai_outputs.get("posts", [])
            }



