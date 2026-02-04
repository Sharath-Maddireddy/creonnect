from typing import Dict, Optional
import os
import time

from backend.app.utils.logger import logger


# ------------------------------------------------
# LLM Client
# ------------------------------------------------

class LLMClientError(Exception):
    """Raised when LLM request fails after retries."""
    pass


class LLMClient:
    """
    Thin abstraction over an LLM provider.
    Can be swapped with QLoRA / local models later.
    Includes timeout and retry logic for production reliability.
    """

    def __init__(
        self,
        model_name: str = "gpt-4o-mini",
        temperature: float = 0.4,
        max_tokens: int = 400,
        timeout: int = 30,
        max_retries: int = 1
    ):
        self.model_name = model_name
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries

        # Lazy import so this file doesn't hard-depend on OpenAI
        try:
            from openai import OpenAI
            api_key = os.getenv("OPENAI_API_KEY")
            if not api_key:
                logger.warning("[LLM] OPENAI_API_KEY not set in environment")
            self._client = OpenAI(api_key=api_key, timeout=timeout)
        except Exception as e:
            logger.error(f"[LLM] Failed to initialize OpenAI client: {e}")
            self._client = None

    def generate(self, prompt: Dict) -> Optional[str]:
        """
        Generate text from the LLM.
        Expects prompt = {"system": "...", "user": "..."}
        Includes timeout and retry logic.
        """

        if self._client is None:
            raise LLMClientError(
                "LLM client not initialized. "
                "Ensure OPENAI_API_KEY is set or replace this client."
            )

        last_error = None
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"[LLM] Request start (attempt {attempt + 1}/{self.max_retries + 1})")
                start_time = time.time()

                response = self._client.chat.completions.create(
                    model=self.model_name,
                    messages=[
                        {"role": "system", "content": prompt["system"]},
                        {"role": "user", "content": prompt["user"]}
                    ],
                    temperature=self.temperature,
                    max_tokens=self.max_tokens
                )

                duration = time.time() - start_time
                logger.info(f"[LLM] Request completed in {duration:.2f}s")

                return response.choices[0].message.content.strip()

            except Exception as e:
                last_error = e
                duration = time.time() - start_time
                logger.warning(f"[LLM] Request failed after {duration:.2f}s: {e}")
                if attempt < self.max_retries:
                    logger.info("[LLM] Retrying...")
                    continue

        # All retries exhausted
        raise LLMClientError(f"LLM request failed after {self.max_retries + 1} attempts: {last_error}")

