from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Optional


_POLICY_NUMBER_RE = re.compile(r"\b(?P<num>\d{2}-\d{7})\b")
_POLICY_WITH_PREFIX_RE = re.compile(r"\bpolizzennr\s+(?P<num>\d{2}-\d{7})\b")

_CLAIM_NUMBER_RE = re.compile(r"\b(?P<clm>clm-\d{4}-\d{4})\b")


@dataclass(frozen=True)
class IdentifierHit:
    kind: str
    value: str
    source: str
    start: int
    end: int
    snippet: str


def find_claim_number(*, subject_c14n: str, body_c14n: str) -> Optional[IdentifierHit]:
    match = _CLAIM_NUMBER_RE.search(subject_c14n)
    if match:
        raw = match.group("clm")
        return IdentifierHit(
            kind="CLAIM_NUMBER",
            value=raw.upper(),
            source="SUBJECT_C14N",
            start=match.start("clm"),
            end=match.end("clm"),
            snippet=raw,
        )

    match = _CLAIM_NUMBER_RE.search(body_c14n)
    if match:
        raw = match.group("clm")
        return IdentifierHit(
            kind="CLAIM_NUMBER",
            value=raw.upper(),
            source="BODY_C14N",
            start=match.start("clm"),
            end=match.end("clm"),
            snippet=raw,
        )

    return None


def find_policy_number(*, subject_c14n: str, body_c14n: str) -> Optional[IdentifierHit]:
    match = _POLICY_NUMBER_RE.search(subject_c14n)
    if match:
        number = match.group("num")
        body_idx = body_c14n.find(number)
        if body_idx != -1:
            return IdentifierHit(
                kind="POLICY_NUMBER",
                value=number,
                source="BODY_C14N",
                start=body_idx,
                end=body_idx + len(number),
                snippet=number,
            )

        return IdentifierHit(
            kind="POLICY_NUMBER",
            value=number,
            source="SUBJECT_C14N",
            start=match.start("num"),
            end=match.end("num"),
            snippet=number,
        )

    match = _POLICY_WITH_PREFIX_RE.search(body_c14n)
    if match:
        number = match.group("num")
        snippet = match.group(0)
        return IdentifierHit(
            kind="POLICY_NUMBER",
            value=number,
            source="BODY_C14N",
            start=match.start(0),
            end=match.end(0),
            snippet=snippet,
        )

    match = _POLICY_NUMBER_RE.search(body_c14n)
    if match:
        number = match.group("num")
        return IdentifierHit(
            kind="POLICY_NUMBER",
            value=number,
            source="BODY_C14N",
            start=match.start("num"),
            end=match.end("num"),
            snippet=number,
        )

    return None

