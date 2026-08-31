"""Caching utilities."""
import math
from functools import wraps
from typing import Any, Callable, Optional, ParamSpec, TypeVar

import orjson
from django.core.cache import cache
from xxhash import xxh128

T = TypeVar("T")
P = ParamSpec("P")


def cached(
    func: Optional[Callable[P, T]] = None,
    *,
    key_attr: Optional[str] = None,
    ttl: Optional[int] = None,
    cache_falsy: bool = True,
) -> Callable:
    """A decorator to cache function call results."""
    cache_key_attr = "_cache_key"

    def _decorator(func: Callable[P, T]) -> Callable[P, Any]:
        """Wrapped decorator."""

        @wraps(func)
        def wrapper(*args: Any, **kwargs: Any) -> Any:
            """Cache return values."""
            if key_attr is None:
                param_str = orjson.dumps(
                    {"args": args, "kwargs": kwargs},
                    default=str,
                ).decode("utf-8")
            else:
                param_str = str(getattr(args[0], key_attr))

            key = xxh128(f"{func.__name__}_{param_str}").hexdigest()
            result = cache.get(key, math.inf)
            if result == math.inf:
                result = func(*args, **kwargs)

                # Add the cache information to the result
                # since the cache keys are very opaque
                if isinstance(result, dict):
                    result[cache_key_attr] = key
                elif hasattr(result, "__dict__"):  # a class
                    setattr(result, cache_key_attr, key)

                if result or cache_falsy:
                    cache.set(key, result, timeout=ttl)
            return result

        return wrapper

    if callable(func):
        return _decorator(func)
    else:
        return _decorator
