from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ieim.audit.file_audit_log import ArtifactRef, FileAuditLogger, build_audit_event
from ieim.hitl.review_store import FileReviewStore, build_review_item
from ieim.raw_store import sha256_prefixed


def _parse_rfc3339(dt: str) -> datetime:
    if dt.endswith("Z"):
        dt = dt[:-1] + "+00:00"
    return datetime.fromisoformat(dt)


def _needs_review(routing: dict) -> bool:
    queue_id = str(routing.get("queue_id") or "")
    actions = set(routing.get("actions") or [])
    if "REVIEW" in queue_id:
        return True
    if bool(routing.get("fail_closed") or False):
        return True
    if "BLOCK_CASE_CREATE" in actions:
        return True
    if "ADD_REQUEST_INFO_DRAFT" in actions or "ADD_REPLY_DRAFT" in actions:
        return True
    return False


@dataclass
class HitlReviewItemsRunner:
    repo_root: Path
    normalized_dir: Path
    attachments_dir: Path
    identity_dir: Path
    classification_dir: Path
    extraction_dir: Path
    routing_dir: Path
    drafts_dir: Path
    hitl_out_dir: Path
    audit_logger: Optional[FileAuditLogger] = None

    def run(self) -> list[dict]:
        produced: list[dict] = []
        store = FileReviewStore(base_dir=self.hitl_out_dir)

        for nm_path in sorted(self.normalized_dir.glob("*.json")):
            nm_bytes = nm_path.read_bytes()
            nm = json.loads(nm_bytes.decode("utf-8"))

            message_id = str(nm["message_id"])
            run_id = str(nm["run_id"])

            identity_path = self.identity_dir / f"{message_id}.identity.json"
            classification_path = self.classification_dir / f"{message_id}.classification.json"
            routing_path = self.routing_dir / f"{message_id}.routing.json"
            extraction_path = self.extraction_dir / f"{message_id}.extraction.json"

            routing_bytes = routing_path.read_bytes()
            routing = json.loads(routing_bytes.decode("utf-8"))
            if not _needs_review(routing):
                continue

            t0 = time.perf_counter()
            item = build_review_item(
                normalized_message_path=nm_path,
                identity_path=identity_path,
                classification_path=classification_path,
                extraction_path=extraction_path,
                routing_path=routing_path,
                drafts_dir=self.drafts_dir,
                attachments_dir=self.attachments_dir,
                created_at=_parse_rfc3339(str(nm["ingested_at"])),
            )
            store_path = store.write(item=item)
            dur_ms = int((time.perf_counter() - t0) * 1000)

            if self.audit_logger is not None:
                input_ref = ArtifactRef(
                    schema_id=str(routing.get("schema_id") or ""),
                    uri=routing_path.name,
                    sha256=sha256_prefixed(routing_bytes),
                )
                out_bytes = store_path.read_bytes()
                output_ref = ArtifactRef(
                    schema_id="REVIEW_ITEM",
                    uri=store_path.name,
                    sha256=sha256_prefixed(out_bytes),
                )
                created_at_dt = _parse_rfc3339(str(nm["ingested_at"]))
                event = build_audit_event(
                    message_id=message_id,
                    run_id=run_id,
                    stage="HITL",
                    actor_type="SYSTEM",
                    created_at=created_at_dt,
                    input_ref=input_ref,
                    output_ref=output_ref,
                    decision_hash=None,
                    config_ref=None,
                    rules_ref=None,
                    model_info=None,
                    evidence=[],
                )
                self.audit_logger.append(event)

            produced.append(
                {
                    "message_id": message_id,
                    "run_id": run_id,
                    "status": "REVIEW_ITEM_CREATED",
                    "duration_ms": dur_ms,
                    "review_item_id": str(item.get("review_item_id") or ""),
                    "queue_id": str(item.get("queue_id") or ""),
                    "path": store_path.as_posix(),
                }
            )

        return produced
