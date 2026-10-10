"""Bounded public execution evidence; never store private model reasoning."""
import json
import re

_secret = re.compile(r"sk-[A-Za-z0-9_.-]+|Bearer\s+\S+", re.I)
_sensitive = re.compile(r"password|api.?key|encrypted|access.?token|authorization|thinking|reasoning", re.I)


def public_value(value, depth=0):
    if depth > 6:
        return "[已折叠]"
    if isinstance(value, dict):
        return {str(k): "[已隐藏]" if _sensitive.search(str(k)) else public_value(v, depth + 1) for k, v in list(value.items())[:40]}
    if isinstance(value, list):
        return [public_value(v, depth + 1) for v in value[:12]]
    if isinstance(value, str):
        # Tool input may embed JSON strings (e.g. body_json).
        try:
            parsed = json.loads(value)
        except (ValueError, TypeError):
            parsed = None
        if isinstance(parsed, (dict, list)):
            return public_value(parsed, depth + 1)
        return _secret.sub("[已隐藏]", value[:1600])
    return value
