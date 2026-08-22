"""Unit tests for LLM client response_format fallback behavior."""

from __future__ import annotations

import sys
from types import SimpleNamespace
from unittest.mock import Mock

import pytest

from backend.app.ai.llm_client import LLMClient, LLMClientError


def _build_llm_client_with_create_mock(create_mock: Mock, max_retries: int = 0) -> LLMClient:
    client = LLMClient.__new__(LLMClient)
    client.model_name = "gpt-4o-mini"
    client.temperature = 0.2
    client.max_tokens = 256
    client.timeout = 30
    client.max_retries = max_retries
    client.retry_base_delay_seconds = 0.5
    client.retry_max_delay_seconds = 8.0
    client._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_mock),
        )
    )
    return client


def _mock_response(content: str | None, finish_reason: str = "stop") -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
                finish_reason=finish_reason,
            )
        ]
    )


def test_generate_retries_once_without_response_format_on_unsupported_error() -> None:
    create_mock = Mock(
        side_effect=[
            Exception("unsupported response_format for this model"),
            _mock_response("hello"),
        ]
    )
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=0)
    prompt = {
        "system": "sys",
        "user": "usr",
        "response_format": {"type": "json_schema"},
    }

    output = llm.generate(prompt)

    assert output == "hello"
    assert create_mock.call_count == 2
    first_call_kwargs = create_mock.call_args_list[0].kwargs
    second_call_kwargs = create_mock.call_args_list[1].kwargs
    assert "response_format" in first_call_kwargs
    assert "response_format" not in second_call_kwargs
    assert prompt["response_format"] == {"type": "json_schema"}


def test_generate_does_not_retry_without_supported_error_signal() -> None:
    create_mock = Mock(side_effect=TimeoutError("request timed out"))
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=0)

    with pytest.raises(LLMClientError) as exc_info:
        llm.generate(
            {
                "system": "sys",
                "user": "usr",
                "response_format": {"type": "json_schema"},
            }
        )

    assert create_mock.call_count == 1
    assert "request timed out" in str(exc_info.value)


def test_generate_fails_fast_for_missing_prompt_key_without_retry() -> None:
    create_mock = Mock()
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=2)

    with pytest.raises(LLMClientError) as exc_info:
        llm.generate({"system": "sys"})

    assert "Missing required prompt key: 'user'" in str(exc_info.value)
    assert create_mock.call_count == 0


def test_generate_uses_exponential_backoff_between_retries(monkeypatch: pytest.MonkeyPatch) -> None:
    create_mock = Mock(
        side_effect=[
            TimeoutError("first timeout"),
            TimeoutError("second timeout"),
            _mock_response("hello"),
        ]
    )
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=2)
    sleep_mock = Mock()
    monkeypatch.setattr("backend.app.ai.llm_client.time.sleep", sleep_mock)

    output = llm.generate({"system": "sys", "user": "usr"})

    assert output == "hello"
    assert create_mock.call_count == 3
    assert [call.args[0] for call in sleep_mock.call_args_list] == [0.5, 1.0]


def test_generate_does_not_log_finetune_dataset_by_default(monkeypatch: pytest.MonkeyPatch) -> None:
    create_mock = Mock(return_value=_mock_response("hello"))
    append_mock = Mock()
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=0)
    monkeypatch.delenv("LLM_LOG_FINETUNE_DATASET", raising=False)
    monkeypatch.setattr("backend.app.ai.llm_client._append_finetune_dataset_record", append_mock)

    output = llm.generate({"system": "sys", "user": "usr"})

    assert output == "hello"
    append_mock.assert_not_called()


def test_generate_logs_finetune_dataset_when_explicitly_enabled(monkeypatch: pytest.MonkeyPatch) -> None:
    create_mock = Mock(return_value=_mock_response("hello"))
    append_mock = Mock()
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=0)
    monkeypatch.setenv("LLM_LOG_FINETUNE_DATASET", "true")
    monkeypatch.setattr("backend.app.ai.llm_client._append_finetune_dataset_record", append_mock)

    output = llm.generate({"system": "sys", "user": "usr"})

    assert output == "hello"
    append_mock.assert_called_once()


def test_generate_raises_on_empty_content_instead_of_returning_empty_string() -> None:
    """Regression: an empty completion (e.g. a reasoning model exhausting its
    token budget on hidden reasoning) must not look like a successful call
    with a blank answer -- callers rely on exceptions to trigger fallback."""
    create_mock = Mock(return_value=_mock_response("", finish_reason="length"))
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=0)

    with pytest.raises(LLMClientError, match="empty content"):
        llm.generate({"system": "sys", "user": "usr"})


def test_generate_raises_on_none_content() -> None:
    create_mock = Mock(return_value=_mock_response(None, finish_reason="content_filter"))
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=0)

    with pytest.raises(LLMClientError, match="empty content"):
        llm.generate({"system": "sys", "user": "usr"})


def test_generate_uses_larger_completion_budget_for_reasoning_models(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("LLM_REASONING_MAX_COMPLETION_TOKENS", raising=False)
    create_mock = Mock(return_value=_mock_response("ok"))
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=0)
    llm.model_name = "gpt-5.6-terra"
    llm.max_tokens = 1200

    llm.generate({"system": "sys", "user": "usr"})

    call_kwargs = create_mock.call_args.kwargs
    assert "temperature" not in call_kwargs
    assert call_kwargs["max_completion_tokens"] >= 4000


def test_generate_reasoning_completion_budget_respects_env_override(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("LLM_REASONING_MAX_COMPLETION_TOKENS", "8000")
    create_mock = Mock(return_value=_mock_response("ok"))
    llm = _build_llm_client_with_create_mock(create_mock=create_mock, max_retries=0)
    llm.model_name = "o1-mini"

    llm.generate({"system": "sys", "user": "usr"})

    assert create_mock.call_args.kwargs["max_completion_tokens"] == 8000


def test_init_uses_env_model_name_when_model_not_provided(monkeypatch: pytest.MonkeyPatch) -> None:
    openai_stub = SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(kwargs=kwargs))
    monkeypatch.setitem(sys.modules, "openai", openai_stub)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("LLM_MODEL_NAME", "ft:test-model")
    client = LLMClient()

    assert client.model_name == "ft:test-model"


def test_init_falls_back_to_default_model_when_env_missing(monkeypatch: pytest.MonkeyPatch) -> None:
    openai_stub = SimpleNamespace(OpenAI=lambda **kwargs: SimpleNamespace(kwargs=kwargs))
    monkeypatch.setitem(sys.modules, "openai", openai_stub)
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("LLM_MODEL_NAME", raising=False)
    client = LLMClient()

    assert client.model_name == LLMClient.DEFAULT_MODEL


def test_init_uses_openrouter_when_explicitly_selected(monkeypatch: pytest.MonkeyPatch) -> None:
    captured: dict[str, object] = {}

    def fake_openai(**kwargs):
        captured.update(kwargs)
        return SimpleNamespace(kwargs=kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=fake_openai))
    monkeypatch.setenv("LLM_PROVIDER", "openrouter")
    monkeypatch.setenv("OPENROUTER_API_KEY", "router-key")
    monkeypatch.setenv("OPENROUTER_APP_URL", "https://app.creonnect.example")
    monkeypatch.setenv("OPENROUTER_APP_NAME", "Creonnect Test")

    client = LLMClient()

    assert client._is_openrouter is True
    assert captured["api_key"] == "router-key"
    assert captured["base_url"] == "https://openrouter.ai/api/v1"
    assert captured["default_headers"] == {
        "HTTP-Referer": "https://app.creonnect.example",
        "X-Title": "Creonnect Test",
    }
