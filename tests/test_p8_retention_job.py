import json
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path

from ieim.ops.retention import run_raw_retention
from ieim.raw_store import FileRawStore, sha256_prefixed


class TestP8RetentionJob(unittest.TestCase):
    def test_raw_retention_deletes_only_expired_unreferenced_artifacts(self) -> None:
        now = datetime(2026, 1, 18, 0, 0, 0, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as td:
            base_dir = Path(td)
            normalized_dir = base_dir / "normalized"
            attachments_dir = base_dir / "attachments"
            normalized_dir.mkdir(parents=True, exist_ok=True)
            attachments_dir.mkdir(parents=True, exist_ok=True)

            store = FileRawStore(base_dir=base_dir)

            # Raw MIME artifacts
            old_mime = store.put_bytes(kind="mime", data=b"old mime", file_extension=".eml")
            new_mime = store.put_bytes(kind="mime", data=b"new mime", file_extension=".eml")

            # Raw attachment bytes
            shared_raw = store.put_bytes(
                kind="attachments", data=b"shared pdf", file_extension=".pdf"
            )
            old_only_raw = store.put_bytes(
                kind="attachments", data=b"old-only pdf", file_extension=".pdf"
            )

            # Derived extracted text artifacts
            shared_text = store.put_bytes(
                kind="attachment_text", data=b"shared text", file_extension=".txt"
            )
            old_only_text = store.put_bytes(
                kind="attachment_text", data=b"old-only text", file_extension=".txt"
            )

            att_shared_id = "att_shared_0000001"
            att_old_id = "att_old_only_00001"
            msg_old = "msg_old_00000000001"
            run_old = "run_old_00000000001"
            msg_new = "msg_new_00000000001"
            run_new = "run_new_00000000001"

            def write_nm(*, message_id: str, run_id: str, ingested_at: datetime, raw_mime_uri: str, raw_mime_sha256: str, attachment_ids: list[str]) -> None:
                nm = {
                    "schema_id": "urn:ieim:schema:normalized-message:1.0.0",
                    "schema_version": "1.0.0",
                    "message_id": message_id,
                    "run_id": run_id,
                    "ingested_at": ingested_at.isoformat().replace("+00:00", "Z"),
                    "received_at": ingested_at.isoformat().replace("+00:00", "Z"),
                    "ingestion_source": "IMAP",
                    "raw_mime_uri": raw_mime_uri,
                    "raw_mime_sha256": raw_mime_sha256,
                    "from_email": "sender@example.test",
                    "to_emails": ["inbox@example.test"],
                    "subject": "test",
                    "subject_c14n": "test",
                    "body_text": "body",
                    "body_text_c14n": "body",
                    "language": "en",
                    "attachment_ids": attachment_ids,
                    "message_fingerprint": sha256_prefixed(message_id.encode("utf-8")),
                }
                (normalized_dir / f"{message_id}.json").write_text(
                    json.dumps(nm, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )

            def write_attachment_artifact(*, attachment_id: str, message_id: str, sha256: str, extracted_text_uri: str, extracted_text_sha256: str) -> None:
                art = {
                    "schema_id": "urn:ieim:schema:attachment-artifact:1.0.0",
                    "schema_version": "1.0.0",
                    "attachment_id": attachment_id,
                    "message_id": message_id,
                    "filename": "file.pdf",
                    "mime_type": "application/pdf",
                    "size_bytes": 123,
                    "sha256": sha256,
                    "av_status": "CLEAN",
                    "extracted_text_uri": extracted_text_uri,
                    "extracted_text_sha256": extracted_text_sha256,
                    "ocr_applied": False,
                    "ocr_confidence": None,
                    "created_at": now.isoformat().replace("+00:00", "Z"),
                    "doc_type_candidates": [],
                }
                (attachments_dir / f"{attachment_id}.artifact.json").write_text(
                    json.dumps(art, indent=2, sort_keys=True) + "\n", encoding="utf-8"
                )

            # Both messages reference the shared attachment; only the old message references old-only.
            write_attachment_artifact(
                attachment_id=att_shared_id,
                message_id=msg_old,
                sha256=shared_raw.sha256,
                extracted_text_uri=shared_text.uri,
                extracted_text_sha256=shared_text.sha256,
            )
            write_attachment_artifact(
                attachment_id=att_old_id,
                message_id=msg_old,
                sha256=old_only_raw.sha256,
                extracted_text_uri=old_only_text.uri,
                extracted_text_sha256=old_only_text.sha256,
            )

            write_nm(
                message_id=msg_old,
                run_id=run_old,
                ingested_at=datetime(2026, 1, 1, 0, 0, 0, tzinfo=timezone.utc),
                raw_mime_uri=old_mime.uri,
                raw_mime_sha256=old_mime.sha256,
                attachment_ids=[att_shared_id, att_old_id],
            )
            write_nm(
                message_id=msg_new,
                run_id=run_new,
                ingested_at=datetime(2026, 1, 17, 0, 0, 0, tzinfo=timezone.utc),
                raw_mime_uri=new_mime.uri,
                raw_mime_sha256=new_mime.sha256,
                attachment_ids=[att_shared_id],
            )

            report = run_raw_retention(
                base_dir=base_dir,
                derived_base_dir=None,
                normalized_dir=normalized_dir,
                attachments_dir=attachments_dir,
                raw_days=5,
                now=now,
                dry_run=False,
                report_path=None,
            )
            self.assertEqual(report.status, "APPLIED")

            # Old raw MIME deleted; new raw MIME retained.
            self.assertFalse((base_dir / old_mime.uri).exists())
            self.assertTrue((base_dir / new_mime.uri).exists())

            # old-only attachment deleted; shared attachment retained.
            self.assertTrue((base_dir / shared_raw.uri).exists())
            self.assertFalse((base_dir / old_only_raw.uri).exists())

            # extracted text: old-only deleted; shared retained.
            self.assertTrue((base_dir / shared_text.uri).exists())
            self.assertFalse((base_dir / old_only_text.uri).exists())


if __name__ == "__main__":
    unittest.main()
