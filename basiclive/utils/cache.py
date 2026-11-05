import hashlib
from functools import wraps
from django.core.cache import cache


def make_key(key, key_prefix, version):
    hashed_key = hashlib.md5(key.encode("utf-8")).hexdigest()
    return f'{key_prefix}:{version}:{hashed_key}'


def cached_method(timeout=300):
    def decorator(method):
        @wraps(method)
        def wrapper(self, *args, **kwargs):
            # Generate a unique cache key based on class, instance PK, method name, and arguments
            args_str = f"{args}:{kwargs}"
            cache_key = f"{self.__class__.__name__}:{self.pk}:{method.__name__}:{args_str}"

            result = cache.get(cache_key)
            if result is None:
                result = method(self, *args, **kwargs)
                cache.set(cache_key, result, timeout)
            return result

        return wrapper

    return decorator
