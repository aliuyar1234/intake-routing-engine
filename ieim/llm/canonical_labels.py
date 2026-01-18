from __future__ import annotations

import re
from functools import lru_cache
from pathlib import Path


@lru_cache(maxsize=1)
def load_canonical_label_sets() -> dict[str, frozenset[str]]:
    root = Path(__file__).resolve().parents[2]
    canonical_path = root / "spec" / "00_CANONICAL.md"
    text = canonical_path.read_text(encoding="utf-8")

    sets: dict[str, set[str]] = {
        "INTENT": set(),
        "PROD": set(),
        "URG": set(),
        "RISK": set(),
        "ENT": set(),
    }

    bullet_re = re.compile(r"^\s*-\s+([A-Z0-9_]+)\b")
    for line in text.splitlines():
        line_s = line.strip()
        m = bullet_re.match(line_s)
        if not m:
            continue
        token = m.group(1)
        if token.startswith("INTENT_"):
            sets["INTENT"].add(token)
        elif token.startswith("PROD_"):
            sets["PROD"].add(token)
        elif token.startswith("URG_"):
            sets["URG"].add(token)
        elif token.startswith("RISK_"):
            sets["RISK"].add(token)
        elif token.startswith("ENT_"):
            sets["ENT"].add(token)

    return {k: frozenset(v) for k, v in sets.items()}


def build_canonical_labels_payload() -> dict:
    sets = load_canonical_label_sets()
    return {
        "intents": sorted(sets["INTENT"]),
        "product_lines": sorted(sets["PROD"]),
        "urgencies": sorted(sets["URG"]),
        "risk_flags": sorted(sets["RISK"]),
        "entity_types": sorted(sets["ENT"]),
    }
