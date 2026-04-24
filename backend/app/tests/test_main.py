from __future__ import annotations

import pytest

from backend import main


def test_validate_brand_api_key_configuration_logs_error_in_test_env(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "test")
    monkeypatch.delenv("BRAND_API_KEY", raising=False)

    messages: list[str] = []
    monkeypatch.setattr(main.logger, "error", lambda message: messages.append(message))

    configured = main._validate_brand_api_key_configuration()

    assert configured is False
    assert messages
    assert "BRAND_API_KEY is not set" in messages[0]


def test_validate_brand_api_key_configuration_raises_in_production(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv("ENV", "production")
    monkeypatch.delenv("BRAND_API_KEY", raising=False)

    with pytest.raises(RuntimeError, match="BRAND_API_KEY is not set"):
        main._validate_brand_api_key_configuration()
