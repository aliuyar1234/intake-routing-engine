from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

import jsonschema

from ieim.raw_store import sha256_prefixed


@dataclass(frozen=True)
class AuditVerification:
    files_checked: int
    events_checked: int
    errors: list[str]

    @property
    def ok(self) -> bool:
        return not self.errors


def _event_hash(event: dict) -> str:
    event_no_hash = {k: v for k, v in event.items() if k != "event_hash"}
    encoded = json.dumps(event_no_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )
    return sha256_prefixed(encoded)


def _load_audit_schema(*, schema_path: Path) -> dict:
    return json.loads(schema_path.read_text(encoding="utf-8"))


def _iter_audit_log_files(audit_dir: Path) -> list[Path]:
    if not audit_dir.exists():
        return []
    return sorted(p for p in audit_dir.rglob("*.jsonl") if p.is_file())


def verify_audit_logs(*, audit_dir: Path, schema_path: Path) -> AuditVerification:
    schema = _load_audit_schema(schema_path=schema_path)
    validator = jsonschema.Draft202012Validator(schema)

    errors: list[str] = []
    files_checked = 0
    events_checked = 0

    for path in _iter_audit_log_files(audit_dir):
        files_checked += 1

        expected_message_id = path.parent.name
        expected_run_id = path.stem

        prev_hash = None
        lines = [ln for ln in path.read_text(encoding="utf-8").splitlines() if ln.strip()]
        if not lines:
            errors.append(f"{path}: empty audit log")
            continue

        for idx, line in enumerate(lines, start=1):
            try:
                event = json.loads(line)
            except Exception as e:
                errors.append(f"{path}:{idx}: invalid json: {e}")
                continue

            try:
                validator.validate(event)
            except Exception as e:
                errors.append(f"{path}:{idx}: schema validation failed: {e}")
                continue

            events_checked += 1

            if str(event.get("message_id")) != expected_message_id:
                errors.append(
                    f"{path}:{idx}: message_id mismatch: {event.get('message_id')} != {expected_message_id}"
                )
            if str(event.get("run_id")) != expected_run_id:
                errors.append(
                    f"{path}:{idx}: run_id mismatch: {event.get('run_id')} != {expected_run_id}"
                )

            if event.get("prev_event_hash") != prev_hash:
                errors.append(
                    f"{path}:{idx}: prev_event_hash mismatch: {event.get('prev_event_hash')} != {prev_hash}"
                )

            expected = _event_hash(event)
            if event.get("event_hash") != expected:
                errors.append(
                    f"{path}:{idx}: event_hash mismatch: {event.get('event_hash')} != {expected}"
                )

            prev_hash = event.get("event_hash")

    return AuditVerification(files_checked=files_checked, events_checked=events_checked, errors=errors)

