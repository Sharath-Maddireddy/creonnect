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


def _is_reasoning_model(model_name: str) -> bool:
    return "5.6" in model_name or "o1" in model_name


def _reasoning_max_completion_tokens(default_max_tokens: int) -> int:
    """Token budget for reasoning models (e.g. gpt-5.6, o1).

    ``max_completion_tokens`` on these models caps hidden reasoning tokens
    *and* the visible answer combined. Reusing a plain-model ``max_tokens``
    default (historically 1200) left rich prompts (like single-post coaching)
    with zero tokens left for visible output after reasoning, so the API
    call "succeeded" with an empty completion and silently fell back to
    generic deterministic text. Give reasoning models a much larger budget,
    tunable via env for further calibration.
    """
    raw = os.getenv("LLM_REASONING_MAX_COMPLETION_TOKENS", "")
    if isinstance(raw, str) and raw.strip():
        try:
            return int(raw.strip())
        except ValueError:
            logger.warning(
                "[LLM] Invalid LLM_REASONING_MAX_COMPLETION_TOKENS=%r; using default", raw
            )
    return max(default_max_tokens, 4000)


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
    Supports Azure OpenAI, direct OpenAI, and OpenRouter's OpenAI-compatible API.

    Provider selection:
      - ``LLM_PROVIDER=openrouter`` → OpenRouter
      - ``LLM_PROVIDER=azure`` → Azure OpenAI
      - ``LLM_PROVIDER=openai`` → direct OpenAI
      - unset / ``auto`` → Azure OpenAI when configured, otherwise direct OpenAI

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
        max_retries: int = 1,
        retry_base_delay_seconds: float = 0.5,
        retry_max_delay_seconds: float = 8.0,
    ):
        self.model_name = model_name or os.getenv("LLM_MODEL_NAME", self.DEFAULT_MODEL)
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.timeout = timeout
        self.max_retries = max_retries
        self.retry_base_delay_seconds = retry_base_delay_seconds
        self.retry_max_delay_seconds = retry_max_delay_seconds
        self._is_azure = False
        self._is_openrouter = False

        # Lazy import so this file doesn't hard-depend on OpenAI
        try:
            provider = os.getenv("LLM_PROVIDER", "auto").strip().lower()
            if provider not in {"auto", "azure", "openai", "openrouter"}:
                raise ValueError(
                    "LLM_PROVIDER must be one of: auto, azure, openai, openrouter"
                )
            azure_endpoint = os.getenv("AZURE_OPENAI_ENDPOINT")

            if provider == "openrouter":
                import httpx
                from openai import OpenAI

                api_key = os.getenv("OPENROUTER_API_KEY")
                if not api_key:
                    logger.warning("[LLM] OPENROUTER_API_KEY not set in environment")
                app_url = os.getenv("OPENROUTER_APP_URL", "").strip()
                app_name = os.getenv("OPENROUTER_APP_NAME", "Creonnect").strip()
                headers = {"X-Title": app_name} if app_name else {}
                if app_url:
                    headers["HTTP-Referer"] = app_url
                self._client = OpenAI(
                    api_key=api_key,
                    base_url="https://openrouter.ai/api/v1",
                    default_headers=headers,
                    timeout=timeout,
                    http_client=httpx.Client(timeout=timeout, trust_env=False),
                )
                self._is_openrouter = True
                logger.info("[LLM] Initialized OpenRouter client (model: %s)", self.model_name)
            elif provider == "azure" or (provider == "auto" and azure_endpoint):
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
            logger.error(f"[LLM] Failed to initialize LLM client: {e}")
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
                "Configure the credentials for the selected LLM_PROVIDER."
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
                    }
                    if _is_reasoning_model(self.model_name):
                        request_payload["max_completion_tokens"] = _reasoning_max_completion_tokens(self.max_tokens)
                        # Do not include temperature for o1/5.6 models
                    else:
                        request_payload["max_tokens"] = self.max_tokens
                        request_payload["temperature"] = self.temperature

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
                
                if not response.choices:
                    raise LLMClientError("LLM returned empty choices -- no response generated")
                raw_content = response.choices[0].message.content
                content = raw_content.strip() if isinstance(raw_content, str) else ""
                if not content:
                    finish_reason = getattr(response.choices[0], "finish_reason", None)
                    raise LLMClientError(
                        "LLM returned empty content "
                        f"(finish_reason={finish_reason!r}); for reasoning models this usually means "
                        "hidden reasoning tokens consumed the entire max_completion_tokens budget "
                        f"(model={self.model_name!r})"
                    )
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
                    self._sleep_before_retry(attempt, "request")
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
                "Configure the credentials for the selected LLM_PROVIDER."
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
                    }
                    if _is_reasoning_model(self.model_name):
                        payload["max_completion_tokens"] = _reasoning_max_completion_tokens(self.max_tokens)
                        # Do not include temperature for o1/5.6 models
                    else:
                        payload["max_tokens"] = self.max_tokens
                        payload["temperature"] = self.temperature

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
                    self._sleep_before_retry(attempt, "tool request")
                    continue

        raise LLMClientError(
            f"LLM tool request failed after {self.max_retries + 1} attempts: {last_error}"
        )

    def _sleep_before_retry(self, attempt: int, label: str) -> None:
        """Sleep with capped exponential backoff before the next retry."""
        delay = min(
            self.retry_max_delay_seconds,
            self.retry_base_delay_seconds * (2 ** max(0, attempt)),
        )
        if delay <= 0:
            logger.info("[LLM] Retrying %s immediately...", label)
            return
        logger.info("[LLM] Retrying %s in %.2fs...", label, delay)
        time.sleep(delay)

    def embed(self, text: str) -> list[float]:
        """Generate a creator-pool embedding vector for the given text."""
        if self._client is None:
            raise LLMClientError(
                "LLM client not initialized. "
                "Configure the credentials for the selected LLM_PROVIDER."
            )

        # Azure requires a deployment name. OpenRouter model IDs are provider
        # specific, so require an explicit embedding model rather than silently
        # sending OpenAI's default model to a router that may not support it.
        if getattr(self, "_is_azure", False):
            embedding_model = os.getenv("AZURE_EMBEDDING_DEPLOYMENT", CREATOR_EMBEDDING_MODEL_NAME)
        elif getattr(self, "_is_openrouter", False):
            embedding_model = os.getenv("OPENROUTER_EMBEDDING_MODEL", "").strip()
            if not embedding_model:
                raise LLMClientError(
                    "OPENROUTER_EMBEDDING_MODEL is required when LLM_PROVIDER=openrouter."
                )
        else:
            embedding_model = CREATOR_EMBEDDING_MODEL_NAME

        start_time = time.time()
        try:
            logger.info("[LLM] Embedding request start (model: %s)", embedding_model)
            response = self._client.embeddings.create(
                input=text,
                model=embedding_model,
                        )
            duration = time.time() - start_time
            logger.info(f"[LLM] Embedding request completed in {duration:.2f}s")
            if not response.data:
                raise LLMClientError("LLM returned empty data -- no embedding generated")
            embedding = response.data[0].embedding
            if len(embedding) != EMBEDDING_DIMENSION:
                raise LLMClientError(
                    "Embedding dimension mismatch: "
                    f"expected {EMBEDDING_DIMENSION} values from {embedding_model}, "
                    f"received {len(embedding)}"
                )
            return embedding
        except Exception as e:
            duration = time.time() - start_time
            logger.warning(f"[LLM] Embedding request failed after {duration:.2f}s: {e}")
            if isinstance(e, LLMClientError):
                raise
            raise LLMClientError(f"Embedding request failed: {e}") from e


