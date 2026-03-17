"""Caching utilities: TTL-aware LRU cache and tactical memoisation."""
from __future__ import annotations

import functools
import time
from typing import Any, Callable, TypeVar

F = TypeVar("F", bound=Callable[..., Any])

# Registry of all TTL-wrapped caches so we can bulk-invalidate them.
_all_caches: list[Callable[[], None]] = []


def entity_cache(maxsize: int = 512, ttl_seconds: int = 300) -> Callable[[F], F]:
    """Decorator that wraps *functools.lru_cache* with a time-to-live.

    After *ttl_seconds* have elapsed the underlying LRU cache is
    transparently cleared so stale DB entities are not served.

    The decorated function gains a ``cache_clear()`` method for manual
    invalidation.
    """

    def decorator(fn: F) -> F:
        last_clear: list[float] = [time.monotonic()]

        @functools.lru_cache(maxsize=maxsize)
        def _cached(*args: Any, **kwargs: Any) -> Any:
            return fn(*args, **kwargs)

        @functools.wraps(fn)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            now = time.monotonic()
            if now - last_clear[0] >= ttl_seconds:
                _cached.cache_clear()
                last_clear[0] = now
            return _cached(*args, **kwargs)

        def cache_clear() -> None:
            _cached.cache_clear()
            last_clear[0] = time.monotonic()

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        _all_caches.append(cache_clear)
        return wrapper  # type: ignore[return-value]

    return decorator


def cache_clear_all() -> None:
    """Invalidate every cache created via :func:`entity_cache` or
    :func:`memoize_match`."""
    for clear_fn in _all_caches:
        clear_fn()


def memoize_match(maxsize: int = 128) -> Callable[[F], F]:
    """Decorator for tactical calculation memoisation.

    The decorated function should accept keyword arguments that form
    the cache key: *formation*, *mentality*, *pressing*,
    *opp_formation*, *opp_pressing*.  All other arguments are passed
    through but **not** included in the key.

    A ``cache_clear()`` method is attached to the wrapper.
    """

    def decorator(fn: F) -> F:
        _cache: dict[tuple[Any, ...], Any] = {}

        @functools.wraps(fn)
        def wrapper(
            *args: Any,
            formation: Any = None,
            mentality: Any = None,
            pressing: Any = None,
            opp_formation: Any = None,
            opp_pressing: Any = None,
            **kwargs: Any,
        ) -> Any:
            key = (formation, mentality, pressing, opp_formation, opp_pressing)
            if key in _cache:
                return _cache[key]
            result = fn(
                *args,
                formation=formation,
                mentality=mentality,
                pressing=pressing,
                opp_formation=opp_formation,
                opp_pressing=opp_pressing,
                **kwargs,
            )
            if len(_cache) >= maxsize:
                # Evict oldest entry (FIFO approximation).
                _cache.pop(next(iter(_cache)))
            _cache[key] = result
            return result

        def cache_clear() -> None:
            _cache.clear()

        wrapper.cache_clear = cache_clear  # type: ignore[attr-defined]
        _all_caches.append(cache_clear)
        return wrapper  # type: ignore[return-value]

    return decorator
