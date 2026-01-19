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
def _correction_schema_id_and_version() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas" / "correction_record.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str) or not schema_id:
        raise ValueError("correction_record.schema.json missing $id")
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


@dataclass(frozen=True)
class StoredCorrectionRecord:
    record: dict
    sha256: str
    path: Path


def build_correction_record(
    *,
    message_id: str,
    run_id: str,
    actor_type: str,
    created_at: datetime,
    corrections: list[dict],
    review_item_id: Optional[str] = None,
    actor_id: Optional[str] = None,
    note: Optional[str] = None,
    artifact_refs: Optional[list[dict]] = None,
    correction_id: Optional[str] = None,
) -> dict:
    schema_id, schema_version = _correction_schema_id_and_version()

    base = {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "message_id": message_id,
        "run_id": run_id,
        "review_item_id": review_item_id,
        "actor_type": actor_type,
        "actor_id": actor_id,
        "created_at": _format_datetime(created_at),
        "note": note,
        "artifact_refs": artifact_refs or [],
        "corrections": list(corrections),
    }

    if correction_id is None:
        correction_id = str(
            uuid.uuid5(
                uuid.NAMESPACE_URL,
                "correction:"
                + message_id
                + ":"
                + run_id
                + ":"
                + str(review_item_id or "")
                + ":"
                + str(actor_type)
                + ":"
                + str(actor_id or "")
                + ":"
                + base["created_at"]
                + ":"
                + sha256_prefixed(_canonical_json_bytes(corrections)),
            )
        )

    base["correction_id"] = correction_id
    return base


def validate_correction_record(*, record: dict, schema_path: Path) -> None:
    try:
        import jsonschema
    except Exception as e:
        raise RuntimeError(f"jsonschema dependency unavailable: {e}") from e

    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    jsonschema.Draft202012Validator(schema).validate(record)


