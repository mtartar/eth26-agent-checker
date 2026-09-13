"""Cache layer.

Why cache at all: verifying a claim can involve several slow external calls
(an LLM round-trip, a subgraph query, a knowledge-graph lookup). Many of
those lookups repeat — the same wallet address or the same entity gets
checked more than once — and on-chain facts about the past don't change.
Caching those lookups is a straightforward, high-value optimization.

Why two backends: production wants Redis (shared across multiple API
instances, survives process restarts). Local development and tests want
something that requires zero setup. Rather than special-casing "if we're in
a test, skip the cache" throughout the codebase, we define one small
interface (`CacheBackend`) and provide two implementations. Every other
module depends only on the interface, never on Redis or dicts directly —
this is the same "depend on an abstraction, not a concrete thing" pattern
you'll see again in app/tools/base.py.
"""

import json
from abc import ABC, abstractmethod
from typing import Any, cast

from app.config import get_settings


class CacheBackend(ABC):
    """Interface every cache implementation depends on instead of on Redis or dicts directly."""

    @abstractmethod
    def get(self, key: str) -> Any | None:
        """Return the cached value for `key`, or `None` if absent."""
        ...

    @abstractmethod
    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Store `value` under `key` for up to `ttl_seconds`."""
        ...


class InMemoryCache(CacheBackend):
    """A plain dict.

    Fine for local dev and tests — not shared across processes, and does not
    honor TTLs (values live as long as the process).
    """

    def __init__(self) -> None:
        """Start with an empty store."""
        self._store: dict[str, Any] = {}

    def get(self, key: str) -> Any | None:
        """Return the cached value for `key`, or `None` if absent."""
        return self._store.get(key)

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Store `value` under `key`. `ttl_seconds` is ignored."""
        self._store[key] = value


class RedisCache(CacheBackend):
    """Backed by a real Redis instance.

    Values are JSON-encoded since Redis stores bytes/strings, not arbitrary
    Python objects.
    """

    def __init__(self, redis_url: str) -> None:
        """Connect to `redis_url`, decoding responses as `str`."""
        import redis  # imported lazily so this module can be imported even
        # if redis-py isn't installed in an environment that never uses it

        self._client = redis.Redis.from_url(redis_url, decode_responses=True)

    def get(self, key: str) -> Any | None:
        """Return the cached value for `key`, or `None` if absent."""
        raw = cast("str | None", self._client.get(key))
        return json.loads(raw) if raw is not None else None

    def set(self, key: str, value: Any, ttl_seconds: int = 3600) -> None:
        """Store `value` under `key` for up to `ttl_seconds`."""
        self._client.set(key, json.dumps(value), ex=ttl_seconds)


_cache_instance: CacheBackend | None = None


def get_cache() -> CacheBackend:
    """Return a process-wide cache instance.

    Chooses the backend based on configuration: Redis if REDIS_URL is set,
    in-memory otherwise.
    """
    global _cache_instance
    if _cache_instance is None:
        settings = get_settings()
        if settings.redis_url:
            _cache_instance = RedisCache(settings.redis_url)
        else:
            _cache_instance = InMemoryCache()
    return _cache_instance
