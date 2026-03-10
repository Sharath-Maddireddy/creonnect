"""Unit tests for LLM client response_format fallback behavior."""

from __future__ import annotations

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
    client._client = SimpleNamespace(
        chat=SimpleNamespace(
            completions=SimpleNamespace(create=create_mock),
        )
    )
    return client


def _mock_response(content: str) -> SimpleNamespace:
    return SimpleNamespace(
        choices=[
            SimpleNamespace(
                message=SimpleNamespace(content=content),
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
