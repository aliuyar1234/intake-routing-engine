from __future__ import annotations

import re


_EMAIL_RE = re.compile(r"(?i)\b[a-z0-9._%+\-]+@[a-z0-9.\-]+\.[a-z]{2,}\b")
_IBAN_RE = re.compile(r"\b[a-z]{2}\d{2}[a-z0-9]{10,30}\b", re.IGNORECASE)


def _mask_ranges(text: str, ranges: list[tuple[int, int]]) -> str:
    if not ranges:
        return text
    chars = list(text)
    for start, end in ranges:
        start = max(0, int(start))
        end = min(len(chars), int(end))
        for i in range(start, end):
            chars[i] = "*"
    return "".join(chars)


def redact_preserve_length(text: str) -> str:
    """Redact common PII patterns while preserving length (stable offsets)."""

    ranges: list[tuple[int, int]] = []
    for pat in [_EMAIL_RE, _IBAN_RE]:
        for m in pat.finditer(text):
            ranges.append((m.start(), m.end()))
    return _mask_ranges(text, ranges)
