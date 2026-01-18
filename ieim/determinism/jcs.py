from __future__ import annotations

import math
from decimal import Decimal
from typing import Any


def _escape_json_string(value: str) -> str:
    out = ['"']
    for ch in value:
        code = ord(ch)
        if ch == '"':
            out.append('\\"')
        elif ch == "\\":
            out.append("\\\\")
        elif code <= 0x1F:
            out.append(f"\\u{code:04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def _canonical_number(value: int | float | Decimal) -> str:
    if isinstance(value, bool):
        raise TypeError("bool is not a JSON number")
    if isinstance(value, int):
        return str(value)
    if isinstance(value, Decimal):
        if not value.is_finite():
            raise ValueError("non-finite Decimal is not supported")
        txt = format(value, "f")
    else:
        if math.isnan(value) or math.isinf(value):
            raise ValueError("non-finite float is not supported")
        txt = repr(float(value))

    if "e" in txt or "E" in txt:
        base, exp = txt.lower().split("e", 1)
        exp = exp.lstrip("+")
        txt = f"{base}e{exp}"

    if "." in txt:
        txt = txt.rstrip("0").rstrip(".")
        if txt == "-0":
            txt = "0"

    return txt


def jcs_bytes(value: Any) -> bytes:
    """RFC8785-like JSON Canonicalization (JCS) for hashing.

    The implementation supports the JSON data model types plus Decimal for numbers.
    """

    if value is None:
        return b"null"
    if value is True:
        return b"true"
    if value is False:
        return b"false"
    if isinstance(value, (int, float, Decimal)) and not isinstance(value, bool):
        return _canonical_number(value).encode("ascii")
    if isinstance(value, str):
        return _escape_json_string(value).encode("utf-8")
    if isinstance(value, list):
        inner = b",".join(jcs_bytes(v) for v in value)
        return b"[" + inner + b"]"
    if isinstance(value, dict):
        parts: list[bytes] = []
        for key in sorted(value.keys()):
            if not isinstance(key, str):
                raise TypeError("JSON object keys must be strings")
            parts.append(_escape_json_string(key).encode("utf-8") + b":" + jcs_bytes(value[key]))
        return b"{" + b",".join(parts) + b"}"
    raise TypeError(f"unsupported type for JCS: {type(value).__name__}")

