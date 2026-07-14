"""Environment variable helpers with python-decouple fallback."""
import os


def _strip_env_value(value):
    """Normalize env values and strip wrapping quotes."""
    if value is None:
        return value
    if isinstance(value, bool) or not isinstance(value, str):
        return value
    text = value.strip()
    if len(text) >= 2 and text[0] == text[-1] and text[0] in {'"', "'"}:
        text = text[1:-1]
    return text


def _fallback_config(key, default=None, cast=None):
    raw = os.getenv(key)
    value = default if raw is None else _strip_env_value(raw)
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
            value = _decouple_config(key, default=default, cast=cast)
        else:
            value = _decouple_config(key, default=default)
        if cast is None or cast is str:
            return _strip_env_value(value)
        return value
except Exception:
    config = _fallback_config
