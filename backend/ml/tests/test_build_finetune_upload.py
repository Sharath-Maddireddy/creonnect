from __future__ import annotations

from backend.ml.build_finetune_upload import _clean_messages
from backend.ml.clean_action_dataset import ChatMessage


def test_clean_messages_supports_dict_and_object_messages() -> None:
    messages = [
        {"role": "system", "content": "rules"},
        ChatMessage(role="user", content="hello"),
        {"role": "assistant", "content": "  "},  # empty assistant should be dropped
        {"role": "assistant", "content": "answer"},
    ]

    cleaned = _clean_messages(messages)

    assert cleaned == [
        {"role": "system", "content": "rules"},
        {"role": "user", "content": "hello"},
        {"role": "assistant", "content": "answer"},
    ]


def test_clean_messages_handles_non_string_content_safely() -> None:
    cleaned = _clean_messages([{"role": "assistant", "content": 123}, {"role": "user", "content": None}])
    assert cleaned == [{"role": "user", "content": ""}]
