from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ieim.raw_store import sha256_prefixed


@dataclass(frozen=True)
class RoutingRuleset:
    ruleset_path: str
    ruleset_sha256: str
    ruleset_version: str
    rules: list[dict[str, Any]]
    fallback: dict[str, Any]


def load_routing_ruleset(*, repo_root: Path, ruleset_path: str) -> RoutingRuleset:
    path = (repo_root / ruleset_path).resolve()
    data = path.read_bytes()
    doc = json.loads(data.decode("utf-8"))

    if not isinstance(doc, dict):
        raise ValueError("routing ruleset must be a JSON object")
    ruleset_version = doc.get("ruleset_version")
    if not isinstance(ruleset_version, str) or not ruleset_version:
        raise ValueError("routing ruleset missing ruleset_version")

    rules = doc.get("rules")
    if not isinstance(rules, list) or not all(isinstance(r, dict) for r in rules):
        raise ValueError("routing ruleset missing rules list")

    fallback = doc.get("fallback")
    if not isinstance(fallback, dict):
        raise ValueError("routing ruleset missing fallback")

    return RoutingRuleset(
        ruleset_path=ruleset_path,
        ruleset_sha256=sha256_prefixed(data),
        ruleset_version=ruleset_version,
        rules=[r for r in rules],
        fallback={k: v for k, v in fallback.items()},
    )

