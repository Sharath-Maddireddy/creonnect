from typing import Any, Dict, Optional
import os
import time

from backend.app.utils.logger import logger


# ------------------------------------------------
# LLM Client
# ------------------------------------------------


def _is_response_format_unsupported_error(err: Exception) -> bool:
    """Return True when error indicates structured output/response_format is unsupported."""
    indicators = [
        "response_format",
        "unsupported response format",
        "unsupported parameter",
        "unknown parameter",
        "invalid parameter",
        "not supported",
        "json schema",
    ]

    fragments: list[str] = [str(err)]
    for attr in ("code", "status_code", "type", "message"):
        value = getattr(err, attr, None)
        if value is not None:
            fragments.append(str(value))

    message_obj = getattr(err, "message", None)
    if isinstance(message_obj, dict):
        for key in ("code", "message", "type", "param"):
            value = message_obj.get(key)
            if value is not None:
                fragments.append(str(value))

    combined = " | ".join(fragments).lower()
    return any(token in combined for token in indicators)


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

    def generate(self, prompt: Dict[str, Any]) -> Optional[str]:
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

        if not isinstance(prompt, dict):
            raise LLMClientError("Prompt must be a dictionary with 'system' and 'user' keys.")
        for key in ("system", "user"):
            if key not in prompt:
                raise LLMClientError(f"Missing required prompt key: '{key}'")

        last_error = None
        skip_response_format = False
        for attempt in range(self.max_retries + 1):
            try:
                logger.info(f"[LLM] Request start (attempt {attempt + 1}/{self.max_retries + 1})")
                start_time = time.time()

                request_payload: dict[str, Any] = {
                    "model": self.model_name,
                    "messages": [
                        {"role": "system", "content": prompt["system"]},
                        {"role": "user", "content": prompt["user"]}
                    ],
                    "temperature": self.temperature,
                    "max_tokens": self.max_tokens,
                }
                response_format = prompt.get("response_format")
                if isinstance(response_format, dict) and not skip_response_format:
                    request_payload["response_format"] = response_format

                try:
                    response = self._client.chat.completions.create(**request_payload)
                except Exception as request_error:
                    # Retry without response_format only for explicit unsupported-format errors.
                    if (
                        "response_format" in request_payload
                        and _is_response_format_unsupported_error(request_error)
                    ):
                        logger.warning(
                            "[LLM] response_format unsupported; retrying request without it: %s",
                            request_error,
                        )
                        skip_response_format = True
                        retry_payload = dict(request_payload)
                        retry_payload.pop("response_format", None)
                        response = self._client.chat.completions.create(**retry_payload)
                    else:
                        raise

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

    def embed(self, text: str) -> list[float] | None:
        """Generate an embedding vector for the given text."""
        if self._client is None:
            logger.error("[LLM] Embedding request failed: client not initialized")
            return None

        start_time = time.time()
        try:
            logger.info("[LLM] Embedding request start")
            response = self._client.embeddings.create(
                input=text,
                model="text-embedding-3-small",
            )
            duration = time.time() - start_time
            logger.info(f"[LLM] Embedding request completed in {duration:.2f}s")
            return response.data[0].embedding
        except Exception as e:
            duration = time.time() - start_time
            logger.warning(f"[LLM] Embedding request failed after {duration:.2f}s: {e}")
            return None



