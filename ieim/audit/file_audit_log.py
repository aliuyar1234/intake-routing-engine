from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

from ieim.raw_store import sha256_prefixed


@lru_cache(maxsize=1)
def _audit_schema_id_and_version() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas" / "audit_event.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str) or not schema_id:
        raise ValueError("audit_event.schema.json missing $id")
    version = schema_id.rsplit(":", 1)[-1]
    return schema_id, version


def _format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _event_hash(event_without_hash: dict) -> str:
    return sha256_prefixed(_canonical_json_bytes(event_without_hash))


@dataclass(frozen=True)
class ArtifactRef:
    schema_id: str
    uri: str
    sha256: str


def build_audit_event(
    *,
    message_id: str,
    run_id: str,
    stage: str,
    actor_type: str,
    created_at: datetime,
    input_ref: ArtifactRef,
    output_ref: ArtifactRef,
    decision_hash: Optional[str] = None,
    config_ref: Optional[dict] = None,
    rules_ref: Optional[dict] = None,
    model_info: Optional[dict] = None,
    evidence: Optional[list[dict]] = None,
) -> dict:
    schema_id, schema_version = _audit_schema_id_and_version()

    audit_event_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"audit:{message_id}:{run_id}:{stage}:{output_ref.sha256}",
        )
    )

    return {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "audit_event_id": audit_event_id,
        "message_id": message_id,
        "run_id": run_id,
        "stage": stage,
        "actor_type": actor_type,
        "actor_id": None,
        "created_at": _format_datetime(created_at),
        "input_ref": {
            "schema_id": input_ref.schema_id,
            "uri": input_ref.uri,
            "sha256": input_ref.sha256,
        },
        "output_ref": {
            "schema_id": output_ref.schema_id,
            "uri": output_ref.uri,
            "sha256": output_ref.sha256,
        },
        "config_ref": config_ref,
        "rules_ref": rules_ref,
        "model_info": model_info,
        "evidence": evidence or [],
        "decision_hash": decision_hash,
        "prev_event_hash": None,
        "event_hash": "sha256:" + ("0" * 64),
    }


class FileAuditLogger:
    """Append-only audit log per (message_id, run_id) with hash chaining."""

    def __init__(self, *, base_dir: Path) -> None:
        self._base_dir = base_dir

    @property
    def base_dir(self) -> Path:
        return self._base_dir

    def _path_for(self, *, message_id: str, run_id: str) -> Path:
        return self._base_dir / "audit" / message_id / f"{run_id}.jsonl"

    def append(self, event: dict) -> dict:
        message_id = event.get("message_id")
        run_id = event.get("run_id")
        if not isinstance(message_id, str) or not isinstance(run_id, str):
            raise ValueError("audit event missing message_id/run_id")

        path = self._path_for(message_id=message_id, run_id=run_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        prev_hash: Optional[str] = None
        if path.exists():
            last_line = None
            with path.open("r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if line:
                        last_line = line
            if last_line:
                prev = json.loads(last_line)
                prev_hash = prev.get("event_hash")

        event["prev_event_hash"] = prev_hash
        event_no_hash = {k: v for k, v in event.items() if k != "event_hash"}
        event["event_hash"] = _event_hash(event_no_hash)

        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
        return event
