from __future__ import annotations

import hashlib


def build_idempotency_key(*, message_fingerprint: str, rule_id: str, rule_version: str, operation: str) -> str:
    """Stable idempotency key derived from routing context (timestamp-free)."""

    raw = f"{message_fingerprint}|{rule_id}|{rule_version}|{operation}".encode("utf-8")
    return "idem:" + hashlib.sha256(raw).hexdigest()

