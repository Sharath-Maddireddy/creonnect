"""Unit tests for in-memory post AI cache repository lock semantics."""

from services.post_ai_cache_repository import PostAICacheRepository


def test_acquire_regen_lock_twice_same_key_second_is_blocked() -> None:
    repo = PostAICacheRepository()

    first = repo.acquire_regen_lock("acct_lock", "media_lock")
    second = repo.acquire_regen_lock("acct_lock", "media_lock")

    assert first is True
    assert second is False


def test_cached_payload_isolation_for_nested_structures() -> None:
    repo = PostAICacheRepository()
    source = {
        "summary": {"text": "hello"},
        "drivers": [{"id": "d1"}],
    }

    repo.set_cached_analysis("acct_nested", "media_nested", source)

    # Mutate source after write; cache should stay unchanged.
    source["summary"]["text"] = "mutated-source"
    source["drivers"][0]["id"] = "mutated-source-driver"

    cached = repo.get_cached_analysis("acct_nested", "media_nested")
    assert isinstance(cached, dict)
    assert cached["summary"]["text"] == "hello"
    assert cached["drivers"][0]["id"] == "d1"

    # Mutate returned payload; cache should stay unchanged.
    cached["summary"]["text"] = "mutated-read"
    cached["drivers"][0]["id"] = "mutated-read-driver"

    cached_again = repo.get_cached_analysis("acct_nested", "media_nested")
    assert isinstance(cached_again, dict)
    assert cached_again["summary"]["text"] == "hello"
    assert cached_again["drivers"][0]["id"] == "d1"
