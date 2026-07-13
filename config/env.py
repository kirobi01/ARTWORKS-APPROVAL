"""Environment variable helpers with python-decouple fallback."""
import os


def _fallback_config(key, default=None, cast=None):
    raw = os.getenv(key)
    value = default if raw is None else raw
    if cast is None:
        return value
    try:
        if cast is bool:
            if isinstance(value, bool):
                return value
            return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}
        if cast is int:
            return int(value)
        if cast is float:
            return float(value)
        return cast(value)
    except Exception:
        return default


try:
    from decouple import config as _decouple_config  # type: ignore

    def config(key, default=None, cast=None):
        if cast is not None:
            return _decouple_config(key, default=default, cast=cast)
        return _decouple_config(key, default=default)
except Exception:
    config = _fallback_config
