#!/usr/bin/env python3
import json
import sys
from pathlib import Path

try:
    import yaml
except Exception as e:
    print(f"DEPENDENCY_UNAVAILABLE: pyyaml: {e}")
    sys.exit(40)

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "spec" / "00_CANONICAL.md"



def strip_wrapping_quotes_or_backticks(val: str) -> str:
    val = val.strip()
    if len(val) >= 2 and ((val[0] == '"' and val[-1] == '"') or (val[0] == '`' and val[-1] == '`')):
        return val[1:-1]
    return val


def parse_canonical_sets(text: str):
    sets = {
        "INTENT": set(),
        "PROD": set(),
        "URG": set(),
        "RISK": set(),
        "DOC": set(),
        "ENT": set(),
        "QUEUE": set(),
        "SLA": set(),
        "IDENTITY": set(),
        "ACTION_VALUES": set(),
        "ID_ENTITY_VALUES": set(),
        "INGESTION_SOURCE_VALUES": set(),
        "AV_STATUS_VALUES": set(),
        "ACTOR_TYPE_VALUES": set()
    }

    for line in text.splitlines():
        line_s = line.strip()
        if not line_s.startswith("-"):
            continue
        # tokens without colon
        if line_s.startswith("- INTENT_"):
            sets["INTENT"].add(line_s.split()[1])
        elif line_s.startswith("- PROD_"):
            sets["PROD"].add(line_s.split()[1])
        elif line_s.startswith("- URG_"):
            sets["URG"].add(line_s.split()[1])
        elif line_s.startswith("- RISK_"):
            sets["RISK"].add(line_s.split()[1])
        elif line_s.startswith("- DOC_"):
            sets["DOC"].add(line_s.split()[1])
        elif line_s.startswith("- ENT_"):
            sets["ENT"].add(line_s.split()[1])
        elif line_s.startswith("- QUEUE_"):
            sets["QUEUE"].add(line_s.split()[1])
        elif line_s.startswith("- SLA_"):
            sets["SLA"].add(line_s.split()[1])
        elif line_s.startswith("- IDENTITY_"):
            sets["IDENTITY"].add(line_s.split()[1])

        # key/value tokens
        if line_s.startswith("- ACTION_") and ":" in line_s:
            val = strip_wrapping_quotes_or_backticks(line_s.split(":", 1)[1])
            sets["ACTION_VALUES"].add(val)
        if line_s.startswith("- ID_ENTITY_") and ":" in line_s:
            val = strip_wrapping_quotes_or_backticks(line_s.split(":", 1)[1])
            sets["ID_ENTITY_VALUES"].add(val)
        if line_s.startswith("- INGESTION_SOURCE_") and ":" in line_s:
            val = strip_wrapping_quotes_or_backticks(line_s.split(":", 1)[1])
            sets["INGESTION_SOURCE_VALUES"].add(val)
        if line_s.startswith("- AV_STATUS_") and ":" in line_s:
            val = strip_wrapping_quotes_or_backticks(line_s.split(":", 1)[1])
            sets["AV_STATUS_VALUES"].add(val)
        if line_s.startswith("- ACTOR_") and ":" in line_s:
            val = strip_wrapping_quotes_or_backticks(line_s.split(":", 1)[1])
            sets["ACTOR_TYPE_VALUES"].add(val)

    return sets


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def walk(obj, path=()):
    if isinstance(obj, dict):
        for k, v in obj.items():
            yield from walk(v, path + (k,))
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            yield from walk(v, path + (str(i),))
    else:
        yield path, obj


def check_json_labels(doc, sets, errors, context_path: str):
    for p, v in walk(doc):
        if isinstance(v, str):
            if v.startswith("INTENT_") and v not in sets["INTENT"]:
                errors.append((context_path, "/".join(p), v))
            elif v.startswith("PROD_") and v not in sets["PROD"]:
                errors.append((context_path, "/".join(p), v))
            elif v.startswith("URG_") and v not in sets["URG"]:
                errors.append((context_path, "/".join(p), v))
            elif v.startswith("RISK_") and v not in sets["RISK"]:
                errors.append((context_path, "/".join(p), v))
            elif v.startswith("DOC_") and v not in sets["DOC"]:
                errors.append((context_path, "/".join(p), v))
            elif v.startswith("ENT_") and v not in sets["ENT"]:
                errors.append((context_path, "/".join(p), v))
            elif v.startswith("QUEUE_") and v not in sets["QUEUE"]:
                errors.append((context_path, "/".join(p), v))
            elif v.startswith("SLA_") and v not in sets["SLA"]:
                errors.append((context_path, "/".join(p), v))
            elif v.startswith("IDENTITY_") and v not in sets["IDENTITY"]:
                errors.append((context_path, "/".join(p), v))

            # Identity candidate entity types are not prefixed; enforce by key context
            if len(p) >= 1 and p[-1] == "entity_type":
                if ("top_k" in p or "selected_candidate" in p):
                    if v not in sets["ID_ENTITY_VALUES"]:
                        errors.append((context_path, "/".join(p), v))

    # Special checks by field name
    if isinstance(doc, dict):
        if "actions" in doc and isinstance(doc["actions"], list):
            for idx, a in enumerate(doc["actions"]):
                if isinstance(a, str) and a not in sets["ACTION_VALUES"]:
                    errors.append((context_path, f"actions/{idx}", a))
        if "ingestion_source" in doc and isinstance(doc["ingestion_source"], str):
            if doc["ingestion_source"] not in sets["INGESTION_SOURCE_VALUES"]:
                errors.append((context_path, "ingestion_source", doc["ingestion_source"]))
        if "av_status" in doc and isinstance(doc["av_status"], str):
            if doc["av_status"] not in sets["AV_STATUS_VALUES"]:
                errors.append((context_path, "av_status", doc["av_status"]))
        if "actor_type" in doc and isinstance(doc["actor_type"], str):
            if doc["actor_type"] not in sets["ACTOR_TYPE_VALUES"]:
                errors.append((context_path, "actor_type", doc["actor_type"]))
        # identity candidate entity types (CUSTOMER/POLICY/CLAIM/CONTACT/BROKER)
        # appear as values of key "entity_type" under "top_k" or "selected_candidate".
        # We enforce them here using path-based checks in the generic traversal below.


def main() -> int:
    if not CANONICAL.exists():
        print("LABEL_CONSISTENCY_FAILED: missing spec/00_CANONICAL.md")
        return 60

    sets = parse_canonical_sets(CANONICAL.read_text(encoding="utf-8", errors="ignore"))

    errors = []

    # Routing ruleset
    routing = ROOT / "configs" / "routing_tables" / "routing_rules_v1.4.1.json"
    if routing.exists():
        check_json_labels(load_json(routing), sets, errors, str(routing.relative_to(ROOT)))

    # Sample emails + attachments + gold
    samples = ROOT / "data" / "samples"
    for p in sorted((samples / "emails").glob("*.json")):
        check_json_labels(load_json(p), sets, errors, str(p.relative_to(ROOT)))

    for p in sorted((samples / "attachments").glob("*.artifact.json")):
        check_json_labels(load_json(p), sets, errors, str(p.relative_to(ROOT)))

    for p in sorted((samples / "gold").glob("*.json")):
        if p.name.endswith(".audit_expectations.json"):
            continue
        check_json_labels(load_json(p), sets, errors, str(p.relative_to(ROOT)))

    # Config YAML (limited checks)
    for cfg in [ROOT / "configs" / "dev.yaml", ROOT / "configs" / "prod.yaml"]:
        if cfg.exists():
            doc = yaml.safe_load(cfg.read_text(encoding="utf-8"))
            check_json_labels(doc, sets, errors, str(cfg.relative_to(ROOT)))

    if errors:
        print("LABEL_CONSISTENCY_FAILED")
        for fp, jp, val in errors[:200]:
            print(f"{fp}:{jp}: {val}")
        return 60

    print("LABEL_CONSISTENCY_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
