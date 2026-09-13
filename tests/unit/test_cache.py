"""Step 4 of PLAN.md — the in-memory cache backend, no Redis needed."""

from app.cache import InMemoryCache


def test_set_then_get_returns_value():
    """A value stored under a key is returned unchanged by a later get."""
    cache = InMemoryCache()
    cache.set("key", {"hello": "world"})
    assert cache.get("key") == {"hello": "world"}


def test_missing_key_returns_none():
    """Getting a key that was never set returns None instead of raising."""
    cache = InMemoryCache()
    assert cache.get("does-not-exist") is None
