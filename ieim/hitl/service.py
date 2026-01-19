from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from ieim.audit.file_audit_log import ArtifactRef, FileAuditLogger, build_audit_event
from ieim.hitl.correction_record import build_correction_record, validate_correction_record
from ieim.raw_store import sha256_prefixed


@dataclass
class FileCorrectionStore:
    base_dir: Path

    def _path_for(self, *, message_id: str, run_id: str, correction_id: str) -> Path:
        return (
            self.base_dir
            / "corrections"
            / message_id
            / run_id
            / f"{correction_id}.correction.json"
        )

    def path_for_record(self, *, record: dict) -> Path:
        message_id = str(record.get("message_id") or "")
        run_id = str(record.get("run_id") or "")
        correction_id = str(record.get("correction_id") or "")
        if not message_id or not run_id or not correction_id:
            raise ValueError("correction record missing message_id/run_id/correction_id")
        return self._path_for(message_id=message_id, run_id=run_id, correction_id=correction_id)

    def write(self, *, record: dict) -> Path:
        message_id = str(record.get("message_id") or "")
        run_id = str(record.get("run_id") or "")
        correction_id = str(record.get("correction_id") or "")
        if not message_id or not run_id or not correction_id:
            raise ValueError("correction record missing message_id/run_id/correction_id")

        path = self._path_for(message_id=message_id, run_id=run_id, correction_id=correction_id)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            raise FileExistsError(f"correction record already exists: {path}")

        out_bytes = (
            json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(out_bytes)
        tmp.replace(path)
        return path


def _now_utc() -> datetime:
    return datetime.now(timezone.utc).replace(microsecond=0)


@dataclass
class HitlService:
    repo_root: Path
    hitl_dir: Path
    audit_logger: Optional[FileAuditLogger] = None

    def _correction_schema_path(self) -> Path:
        return self.repo_root / "schemas" / "correction_record.schema.json"

    def submit_correction(
        self,
        *,
        review_item_path: Path,
        actor_id: str,
        corrections: list[dict],
        note: Optional[str] = None,
        created_at: Optional[datetime] = None,
        correction_id: Optional[str] = None,
    ) -> Path:
        created_at = created_at or _now_utc()

        review_bytes = review_item_path.read_bytes()
        review = json.loads(review_bytes.decode("utf-8"))

        message_id = str(review.get("message_id") or "")
        run_id = str(review.get("run_id") or "")
        review_item_id = str(review.get("review_item_id") or "")
        if not message_id or not run_id or not review_item_id:
            raise ValueError("review item missing message_id/run_id/review_item_id")

        record = build_correction_record(
            message_id=message_id,
            run_id=run_id,
            review_item_id=review_item_id,
            actor_type="HUMAN",
            actor_id=actor_id,
            created_at=created_at,
            note=note,
            artifact_refs=list(review.get("artifact_refs") or []),
            corrections=corrections,
            correction_id=correction_id,
        )

        validate_correction_record(record=record, schema_path=self._correction_schema_path())

        store = FileCorrectionStore(base_dir=self.hitl_dir)
        expected_path = store.path_for_record(record=record)
        if expected_path.exists():
            existing_bytes = expected_path.read_bytes()
            expected_bytes = (
                json.dumps(record, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
            )
            if sha256_prefixed(existing_bytes) != sha256_prefixed(expected_bytes):
                raise RuntimeError("immutability violation: correction record exists with different content")
            return expected_path

        path = store.write(record=record)

        if self.audit_logger is not None:
            input_ref = ArtifactRef(
                schema_id="REVIEW_ITEM",
                uri=review_item_path.name,
                sha256=sha256_prefixed(review_bytes),
            )
            out_bytes = path.read_bytes()
            output_ref = ArtifactRef(
                schema_id=str(record["schema_id"]),
                uri=path.name,
                sha256=sha256_prefixed(out_bytes),
            )
            event = build_audit_event(
                message_id=message_id,
                run_id=run_id,
                stage="HITL",
                actor_type="HUMAN",
                created_at=created_at,
                input_ref=input_ref,
                output_ref=output_ref,
                decision_hash=None,
                evidence=[],
            )
            event["actor_id"] = actor_id
            self.audit_logger.append(event)

        return path
