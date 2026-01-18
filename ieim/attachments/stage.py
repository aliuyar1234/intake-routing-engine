from __future__ import annotations

import json
import mimetypes
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ieim.attachments.av import AVScanner
from ieim.attachments.ocr import OCRProcessor
from ieim.audit.file_audit_log import ArtifactRef
from ieim.ingest.adapter import MailIngestAdapter, MessageRef
from ieim.raw_store import FileRawStore, sha256_prefixed


@lru_cache(maxsize=1)
def _attachment_schema_id_and_version() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas" / "attachment_artifact.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str) or not schema_id:
        raise ValueError("attachment_artifact.schema.json missing $id")
    version = schema_id.rsplit(":", 1)[-1]
    return schema_id, version


def _format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _derive_attachment_id(*, message_id: str, source_attachment_id: str, sha256: str) -> str:
    try:
        uuid.UUID(source_attachment_id)
        return source_attachment_id
    except Exception:
        return str(uuid.uuid5(uuid.NAMESPACE_URL, f"att:{message_id}:{source_attachment_id}:{sha256}"))


def _best_effort_mime_type(*, filename: str, declared: str) -> str:
    if declared:
        return declared
    guessed, _enc = mimetypes.guess_type(filename)
    return guessed or "application/octet-stream"


def _extract_text(*, mime_type: str, data: bytes) -> Optional[str]:
    if not mime_type.startswith("text/"):
        return None
    return data.decode("utf-8", errors="replace")


@dataclass
class AttachmentStage:
    adapter: MailIngestAdapter
    raw_store: FileRawStore
    derived_store: FileRawStore
    av_scanner: AVScanner
    attachments_out_dir: Path
    ocr_processor: Optional[OCRProcessor] = None
    def process_message(
        self,
        *,
        message_id: str,
        source_ref: MessageRef,
        created_at: datetime,
    ) -> list["ProcessedAttachment"]:
        schema_id, schema_version = _attachment_schema_id_and_version()
        created_at_s = _format_datetime(created_at)

        processed: list[ProcessedAttachment] = []
        for att in self.adapter.list_attachments(source_ref):
            data = self.adapter.fetch_attachment_bytes(att)
            sha = sha256_prefixed(data)

            ext = Path(att.filename).suffix if att.filename else ""
            put = self.raw_store.put_bytes(kind="attachments", data=data, file_extension=ext or None)

            mime_type = _best_effort_mime_type(filename=att.filename, declared=att.mime_type)
            av_status = self.av_scanner.scan(data=data, filename=att.filename, mime_type=mime_type)

            extracted_text_uri = None
            extracted_text_sha256 = None
            ocr_applied = False
            ocr_confidence = None

            if av_status == "CLEAN":
                extracted = _extract_text(mime_type=mime_type, data=data)
                if extracted is not None:
                    text_bytes = extracted.encode("utf-8")
                    tput = self.derived_store.put_bytes(
                        kind="attachment_text", data=text_bytes, file_extension=".txt"
                    )
                    extracted_text_uri = tput.uri
                    extracted_text_sha256 = tput.sha256
                elif self.ocr_processor is not None:
                    ocr = self.ocr_processor.ocr(
                        data=data, filename=att.filename, mime_type=mime_type
                    )
                    if ocr is not None:
                        text_bytes = ocr.text.encode("utf-8")
                        tput = self.derived_store.put_bytes(
                            kind="attachment_text", data=text_bytes, file_extension=".txt"
                        )
                        extracted_text_uri = tput.uri
                        extracted_text_sha256 = tput.sha256
                        ocr_applied = True
                        ocr_confidence = float(ocr.confidence)

            attachment_id = _derive_attachment_id(
                message_id=message_id, source_attachment_id=att.attachment_id, sha256=sha
            )

            artifact = {
                "schema_id": schema_id,
                "schema_version": schema_version,
                "attachment_id": attachment_id,
                "message_id": message_id,
                "filename": att.filename,
                "mime_type": mime_type,
                "size_bytes": len(data),
                "sha256": sha,
                "av_status": av_status,
                "extracted_text_uri": extracted_text_uri,
                "extracted_text_sha256": extracted_text_sha256,
                "ocr_applied": ocr_applied,
                "ocr_confidence": ocr_confidence,
                "doc_type_candidates": [],
                "created_at": created_at_s,
            }

            self.attachments_out_dir.mkdir(parents=True, exist_ok=True)
            artifact_path = self.attachments_out_dir / f"{attachment_id}.artifact.json"
            if not artifact_path.exists():
                artifact_bytes = (
                    json.dumps(artifact, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
                    + b"\n"
                )
                tmp = artifact_path.with_suffix(artifact_path.suffix + ".tmp")
                tmp.write_bytes(artifact_bytes)
                tmp.replace(artifact_path)
            else:
                artifact_bytes = artifact_path.read_bytes()

            raw_ref = ArtifactRef(schema_id="RAW_ATTACHMENT", uri=put.uri, sha256=put.sha256)
            out_ref = ArtifactRef(
                schema_id=schema_id, uri=artifact_path.name, sha256=sha256_prefixed(artifact_bytes)
            )
            processed.append(
                ProcessedAttachment(
                    attachment_id=attachment_id, raw_ref=raw_ref, artifact_ref=out_ref
                )
            )

        return processed


@dataclass(frozen=True)
class ProcessedAttachment:
    attachment_id: str
    raw_ref: ArtifactRef
    artifact_ref: ArtifactRef
