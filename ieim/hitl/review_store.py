from __future__ import annotations

import json
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ieim.raw_store import sha256_prefixed


def _format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _canonical_json_bytes(obj: Any) -> bytes:
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode(
        "utf-8"
    )


def _artifact_ref_from_json_bytes(*, uri: str, data: bytes) -> dict:
    obj = json.loads(data.decode("utf-8"))
    schema_id = obj.get("schema_id")
    if not isinstance(schema_id, str) or not schema_id:
        raise ValueError(f"artifact missing schema_id: {uri}")
    return {"schema_id": schema_id, "uri": uri, "sha256": sha256_prefixed(data)}


def build_review_item(
    *,
    normalized_message_path: Path,
    identity_path: Path,
    classification_path: Path,
    routing_path: Path,
    extraction_path: Optional[Path] = None,
    drafts_dir: Optional[Path] = None,
    attachments_dir: Optional[Path] = None,
    created_at: Optional[datetime] = None,
) -> dict:
    nm_bytes = normalized_message_path.read_bytes()
    nm = json.loads(nm_bytes.decode("utf-8"))

    message_id = str(nm["message_id"])
    run_id = str(nm["run_id"])

    identity_bytes = identity_path.read_bytes()
    cls_bytes = classification_path.read_bytes()
    routing_bytes = routing_path.read_bytes()

    identity = json.loads(identity_bytes.decode("utf-8"))
    cls = json.loads(cls_bytes.decode("utf-8"))
    routing = json.loads(routing_bytes.decode("utf-8"))

    queue_id = str(routing.get("queue_id") or "")
    routing_sha = sha256_prefixed(routing_bytes)

    review_item_id = str(
        uuid.uuid5(
            uuid.NAMESPACE_URL,
            f"review:{message_id}:{run_id}:{queue_id}:{routing_sha}",
        )
    )

    if created_at is None:
        created_at = datetime.fromisoformat(str(nm["ingested_at"]).replace("Z", "+00:00"))

    artifact_refs: list[dict] = [
        _artifact_ref_from_json_bytes(uri=normalized_message_path.name, data=nm_bytes),
        _artifact_ref_from_json_bytes(uri=identity_path.name, data=identity_bytes),
        _artifact_ref_from_json_bytes(uri=classification_path.name, data=cls_bytes),
        _artifact_ref_from_json_bytes(uri=routing_path.name, data=routing_bytes),
    ]

    if extraction_path is not None and extraction_path.exists():
        ext_bytes = extraction_path.read_bytes()
        artifact_refs.append(_artifact_ref_from_json_bytes(uri=extraction_path.name, data=ext_bytes))

    raw_mime_uri = str(nm.get("raw_mime_uri") or "")
    raw_mime_sha256 = str(nm.get("raw_mime_sha256") or "")
    if raw_mime_uri and raw_mime_sha256:
        artifact_refs.append({"schema_id": "RAW_MIME", "uri": raw_mime_uri, "sha256": raw_mime_sha256})

    if attachments_dir is not None:
        for att_id in nm.get("attachment_ids") or []:
            artifact_path = attachments_dir / f"{att_id}.artifact.json"
            if not artifact_path.exists():
                continue
            att_bytes = artifact_path.read_bytes()
            artifact_refs.append(
                _artifact_ref_from_json_bytes(uri=artifact_path.name, data=att_bytes)
            )

    draft_refs: list[dict] = []
    if drafts_dir is not None:
        for suffix, schema_id in [
            ("request_info.md", "DRAFT_REQUEST_INFO"),
            ("reply.md", "DRAFT_REPLY"),
        ]:
            path = drafts_dir / f"{message_id}.{suffix}"
            if not path.exists():
                continue
            b = path.read_bytes()
            draft_refs.append({"schema_id": schema_id, "uri": path.name, "sha256": sha256_prefixed(b)})

    return {
        "review_item_id": review_item_id,
        "message_id": message_id,
        "run_id": run_id,
        "queue_id": queue_id,
        "created_at": _format_datetime(created_at),
        "status": "OPEN",
        "routing": {
            "rule_id": str(routing.get("rule_id") or ""),
            "rule_version": str(routing.get("rule_version") or ""),
            "fail_closed": bool(routing.get("fail_closed") or False),
            "fail_closed_reason": routing.get("fail_closed_reason"),
        },
        "identity_status": str(identity.get("status") or ""),
        "primary_intent": str((cls.get("primary_intent") or {}).get("label") or ""),
        "artifact_refs": artifact_refs,
        "draft_refs": draft_refs,
    }


@dataclass
class FileReviewStore:
    base_dir: Path

    def _path_for(self, *, queue_id: str, review_item_id: str) -> Path:
        return self.base_dir / "review_items" / queue_id / f"{review_item_id}.review.json"

    def write(self, *, item: dict) -> Path:
        queue_id = str(item.get("queue_id") or "")
        review_item_id = str(item.get("review_item_id") or "")
        if not queue_id or not review_item_id:
            raise ValueError("review item missing queue_id/review_item_id")

        path = self._path_for(queue_id=queue_id, review_item_id=review_item_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        if path.exists():
            return path

        out_bytes = (
            json.dumps(item, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8") + b"\n"
        )
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(out_bytes)
        tmp.replace(path)
        return path

    def list_queue(self, *, queue_id: str) -> list[dict]:
        qdir = self.base_dir / "review_items" / queue_id
        if not qdir.exists():
            return []
        items = []
        for p in sorted(qdir.glob("*.review.json")):
            items.append(json.loads(p.read_text(encoding="utf-8")))
        return items

    def find(self, *, review_item_id: str) -> Optional[dict]:
        root = self.base_dir / "review_items"
        if not root.exists():
            return None
        for p in root.rglob(f"{review_item_id}.review.json"):
            return json.loads(p.read_text(encoding="utf-8"))
        return None

    def find_path(self, *, review_item_id: str) -> Optional[Path]:
        root = self.base_dir / "review_items"
        if not root.exists():
            return None
        for p in root.rglob(f"{review_item_id}.review.json"):
            return p
        return None
