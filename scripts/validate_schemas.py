#!/usr/bin/env python3
import json
import sys
from pathlib import Path

try:
    import jsonschema
except Exception as e:
    print(f"DEPENDENCY_UNAVAILABLE: jsonschema: {e}")
    sys.exit(40)

ROOT = Path(__file__).resolve().parents[1]
CANONICAL = ROOT / "spec" / "00_CANONICAL.md"
SCHEMAS_DIR = ROOT / "schemas"

FILE_TO_CANONICAL_KEY = {
    "normalized_message.schema.json": "SCHEMA_ID_NORMALIZED_MESSAGE",
    "attachment_artifact.schema.json": "SCHEMA_ID_ATTACHMENT_ARTIFACT",
    "identity_resolution_result.schema.json": "SCHEMA_ID_IDENTITY_RESULT",
    "classification_result.schema.json": "SCHEMA_ID_CLASSIFICATION_RESULT",
    "extraction_result.schema.json": "SCHEMA_ID_EXTRACTION_RESULT",
    "routing_decision.schema.json": "SCHEMA_ID_ROUTING_DECISION",
    "audit_event.schema.json": "SCHEMA_ID_AUDIT_EVENT",
    "correction_record.schema.json": "SCHEMA_ID_CORRECTION_RECORD",
    "loadtest_report.schema.json": "SCHEMA_ID_LOADTEST_REPORT",
}


def parse_canonical_schema_ids(text: str):
    ids = {}
    for line in text.splitlines():
        line = line.strip()
        if not line.startswith("- SCHEMA_ID_"):
            continue
        # pattern: - SCHEMA_ID_X: "urn:ieim:schema:sample:1.0.0"
        parts = line.split(":", 1)
        if len(parts) != 2:
            continue
        key = parts[0].strip()[2:]  # remove leading "- "
        val = parts[1].strip()
        if val.startswith('"') and val.endswith('"'):
            val = val[1:-1]
        ids[key] = val
    return ids


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def validate_schema_file(path: Path):
    schema = load_json(path)
    jsonschema.Draft202012Validator.check_schema(schema)
    return schema


def validate_instance(schema: dict, instance_path: Path):
    inst = load_json(instance_path)
    v = jsonschema.Draft202012Validator(schema)
    errors = sorted(v.iter_errors(inst), key=lambda e: e.path)
    if errors:
        msg = errors[0]
        raise ValueError(f"{instance_path}: {msg.message}")


def main() -> int:
    if not CANONICAL.exists():
        print("SCHEMA_VALIDATION_FAILED: missing spec/00_CANONICAL.md")
        return 20

    canonical_text = CANONICAL.read_text(encoding="utf-8", errors="ignore")
    canonical_ids = parse_canonical_schema_ids(canonical_text)

    # Load and validate all schemas
    schemas = {}
    for filename, canonical_key in FILE_TO_CANONICAL_KEY.items():
        p = SCHEMAS_DIR / filename
        if not p.exists():
            print(f"SCHEMA_VALIDATION_FAILED: missing {p}")
            return 20
        schema = validate_schema_file(p)
        expected_id = canonical_ids.get(canonical_key)
        if not expected_id:
            print(f"SCHEMA_VALIDATION_FAILED: canonical key missing: {canonical_key}")
            return 20
        if schema.get("$id") != expected_id:
            print(f"SCHEMA_VALIDATION_FAILED: $id mismatch in {filename}: {schema.get('$id')} != {expected_id}")
            return 20
        schemas[filename] = schema

    # Validate sample instances
    samples = ROOT / "data" / "samples"
    emails_dir = samples / "emails"
    atts_dir = samples / "attachments"
    gold_dir = samples / "gold"

    for p in sorted(emails_dir.glob("*.json")):
        validate_instance(schemas["normalized_message.schema.json"], p)

    for p in sorted(atts_dir.glob("*.artifact.json")):
        validate_instance(schemas["attachment_artifact.schema.json"], p)

    for p in sorted(gold_dir.glob("*.identity.json")):
        validate_instance(schemas["identity_resolution_result.schema.json"], p)

    for p in sorted(gold_dir.glob("*.classification.json")):
        validate_instance(schemas["classification_result.schema.json"], p)

    for p in sorted(gold_dir.glob("*.extraction.json")):
        validate_instance(schemas["extraction_result.schema.json"], p)

    for p in sorted(gold_dir.glob("*.routing.json")):
        validate_instance(schemas["routing_decision.schema.json"], p)

    print("SCHEMA_VALIDATION_OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
