from typing import Any, Dict, Optional
import os
import time

from backend.app.infra.models import CREATOR_EMBEDDING_MODEL_NAME, EMBEDDING_DIMENSION
from backend.app.utils.logger import logger
from backend.app.ai.circuit_breaker import openai_circuit_breaker, CircuitBreakerOpen


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


def _should_log_finetune_dataset() -> bool:
    raw = os.getenv("LLM_LOG_FINETUNE_DATASET", "")
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _append_finetune_dataset_record(prompt: Dict[str, Any], content: str) -> None:
    import json
    from pathlib import Path

    repo_root = Path(__file__).resolve().parents[3]
    artifact_dir = repo_root / "internal_tools" / "artifacts"
    artifact_dir.mkdir(parents=True, exist_ok=True)
    dataset_path = artifact_dir / "finetune_dataset.jsonl"
    record = {
        "messages": [
            {"role": "system", "content": prompt.get("system", "")},
            {"role": "user", "content": prompt.get("user", "")},
            {"role": "assistant", "content": content},
        ]
    }
    with open(dataset_path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, ensure_ascii=False) + "\n")


class LLMClient:
    """
    Thin abstraction over an LLM provider.
    Supports both Azure OpenAI and direct OpenAI API.

    Provider selection (automatic):
      - If AZURE_OPENAI_ENDPOINT is set → uses Azure OpenAI (credits pay)
      - Otherwise → falls back to direct OpenAI API

    Can be swapped with QLoRA / local models later.
    Includes timeout and retry logic for production reliability.
    """

    DEFAULT_MODEL = "gpt-4o-mini"

    def __init__(
        self,
        model_name: str | None = None,
        temperature: float = 0.4,
        max_tokens: int = 1200,
        timeout: int = 30,
        max_retries: int = 1
    ):
        self.model_name = model_name or os.getenv("LLM_MODEL_NAME", self.DEFAULT_MODEL)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self._is_azure = False

        # Lazy import so this file doesn't hard-depend on OpenAI
        try:
            azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

            if azure_endpoint:
                # ── Azure OpenAI path (uses Azure credits) ──
                from openai import AzureOpenAI
                azure_key = os.getenv("AZURE_OPENAI_API_KEY")
                api_version = os.getenv("AZURE_OPENAI_API_VERSION", "2024-10-21")
                if not azure_key:
                    logger.warning("[LLM] AZURE_OPENAI_API_KEY not set in environment")
                self._client = AzureOpenAI(
                    api_key=azure_key,
                    api_version=api_version,
                    azure_endpoint=azure_endpoint,
                    timeout=timeout,
                )
                self._is_azure = True
                logger.info(
                    "[LLM] Initialized Azure OpenAI client → %s (model: %s)",
                    azure_endpoint, self.model_name,
                )
            else:
                # ── Direct OpenAI fallback ──
                import httpx
                from openai import OpenAI
                api_key = os.getenv("OPENAI_API_KEY")
                if not api_key:
                    logger.warning("[LLM] OPENAI_API_KEY not set in environment")
                self._client = OpenAI(
                    api_key=api_key,
                    timeout=timeout,
                    http_client=httpx.Client(timeout=timeout, trust_env=False),
                )
                logger.info("[LLM] Initialized direct OpenAI client (model: %s)", self.model_name)
        except Exception as e:
            logger.error(f"[LLM] Failed to initialize OpenAI client: {e}")
            self._client = None

    @property
    def client(self) -> Any | None:
        """Expose the underlying OpenAI client for structured-output calls."""
        return self._client

    @property
    def model(self) -> str:
        """Return the model name for external inspection."""
        return self.model_name

    def generate(self, prompt: Dict[str, Any]) -> Optional[str]:
        """
        Generate text from the LLM.
        Expects prompt = {"system": "...", "user": "..."}
        Includes timeout and retry logic, plus circuit breaker for resilience.
        """

        if self._client is None:
            raise LLMClientError(
                "LLM client not initialized. "
                "Ensure OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT is set."
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

                # Wrap API call with circuit breaker
                def _make_api_call():
                    nonlocal skip_response_format
                    request_payload: dict[str, Any] = {
                        "model": self.model_name,
                        "messages": [
                            {"role": "system", "content": prompt["system"]},
                            {"role": "user", "content": prompt["user"]}
                        ],
                        "temperature": self.temperature,
                    }
                    if "5.6" in self.model_name or "o1" in self.model_name:
                        request_payload["max_completion_tokens"] = self.max_tokens
                    else:
                        request_payload["max_tokens"] = self.max_tokens

                    response_format = prompt.get("response_format")
                    if isinstance(response_format, dict) and not skip_response_format:
                        request_payload["response_format"] = response_format

                    try:
                        return self._client.chat.completions.create(**request_payload)
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
                            return self._client.chat.completions.create(**retry_payload)
                        else:
                            raise

                try:
                    response = openai_circuit_breaker.call(_make_api_call)
                except CircuitBreakerOpen as cb_error:
                    logger.error(f"[LLM] Circuit breaker rejected request: {cb_error}")
                    raise LLMClientError(str(cb_error))

                duration = time.time() - start_time
                logger.info(f"[LLM] Request completed in {duration:.2f}s")
                
                content = response.choices[0].message.content.strip()
                try:
                    if _should_log_finetune_dataset():
                        _append_finetune_dataset_record(prompt, content)
                except Exception as log_err:
                    logger.warning(f"[LLM] Failed to write fine-tuning dataset: {log_err}")
                
                return content

            except Exception as e:
                last_error = e
                duration = time.time() - start_time
                logger.warning(f"[LLM] Request failed after {duration:.2f}s: {e}")
                if attempt < self.max_retries:
                    logger.info("[LLM] Retrying...")
                    continue

        # All retries exhausted
        raise LLMClientError(f"LLM request failed after {self.max_retries + 1} attempts: {last_error}")


    def generate_with_tools(
        self,
        messages: list[dict[str, Any]],
        tools: list[dict[str, Any]],
        *,
        tool_choice: str = "auto",
    ) -> Any:
        """
        Call the chat completions API with tool/function definitions.
        Returns the raw response object so the caller can inspect tool_calls.

        Includes the same circuit breaker and retry logic as generate().
        """
        if self._client is None:
            raise LLMClientError(
                "LLM client not initialized. "
                "Ensure OPENAI_API_KEY or AZURE_OPENAI_ENDPOINT is set."
            )

        if not isinstance(messages, list) or not messages:
            raise LLMClientError("messages must be a non-empty list.")
        if not isinstance(tools, list):
            raise LLMClientError("tools must be a list.")
        if not isinstance(tool_choice, str) or not tool_choice.strip():
            raise LLMClientError("tool_choice must be a non-empty string.")

        last_error = None
        for attempt in range(self.max_retries + 1):
            start_time = time.time()
            try:
                logger.info(
                    "[LLM] Tool request start (attempt %s/%s)",
                    attempt + 1,
                    self.max_retries + 1,
                )

                def _make_api_call():
                    payload = {
                        "model": self.model_name,
                        "messages": messages,
                        "tools": tools,
                        "tool_choice": tool_choice,
                        "temperature": self.temperature,
                    }
                    if "5.6" in self.model_name or "o1" in self.model_name:
                        payload["max_completion_tokens"] = self.max_tokens
                    else:
                        payload["max_tokens"] = self.max_tokens

                    return self._client.chat.completions.create(**payload)

                try:
                    response = openai_circuit_breaker.call(_make_api_call)
                except CircuitBreakerOpen as cb_error:
                    logger.error("[LLM] Circuit breaker rejected tool request: %s", cb_error)
                    raise LLMClientError(str(cb_error))

                duration = time.time() - start_time
                logger.info("[LLM] Tool request completed in %.2fs", duration)
                return response
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                duration = time.time() - start_time
                logger.warning("[LLM] Tool request failed after %.2fs: %s", duration, exc)
                if attempt < self.max_retries:
                    logger.info("[LLM] Retrying tool request...")
                    continue

        raise LLMClientError(
            f"LLM tool request failed after {self.max_retries + 1} attempts: {last_error}"
        )

    def embed(self, text: str) -> list[float] | None:
        """Generate a creator-pool embedding vector for the given text."""
        if self._client is None:
            logger.error("[LLM] Embedding request failed: client not initialized")
            return None

        # On Azure, use the embedding deployment name; on direct OpenAI, use the model name
        embedding_model = (
            os.getenv("AZURE_EMBEDDING_DEPLOYMENT", CREATOR_EMBEDDING_MODEL_NAME)
            if self._is_azure
            else CREATOR_EMBEDDING_MODEL_NAME
        )

        start_time = time.time()
        try:
            logger.info("[LLM] Embedding request start (model: %s)", embedding_model)
            response = self._client.embeddings.create(
                input=text,
                model=embedding_model,
            )
            duration = time.time() - start_time
            logger.info(f"[LLM] Embedding request completed in {duration:.2f}s")
            embedding = response.data[0].embedding
            if len(embedding) != EMBEDDING_DIMENSION:
                logger.error(
                    "[LLM] Embedding dimension mismatch: expected %s values from %s, received %s",
                    EMBEDDING_DIMENSION,
                    embedding_model,
                    len(embedding),
                )
                return None
            return embedding
        except Exception as e:
            duration = time.time() - start_time
            logger.warning(f"[LLM] Embedding request failed after {duration:.2f}s: {e}")
            return None


