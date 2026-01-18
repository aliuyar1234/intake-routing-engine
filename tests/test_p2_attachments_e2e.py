import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from ieim.attachments.av import Sha256MappingAVScanner
from ieim.attachments.stage import AttachmentStage
from ieim.audit.file_audit_log import FileAuditLogger
from ieim.ingest.filesystem_adapter import FilesystemMailIngestAdapter
from ieim.pipeline.p1_ingest_normalize import IngestNormalizeRunner
from ieim.raw_store import FileRawStore


class TestP2AttachmentsE2E(unittest.TestCase):
    def test_attachment_artifacts_av_enforcement_and_audit(self) -> None:
        root = Path(__file__).resolve().parents[1]

        nm_schema = json.loads((root / "schemas" / "normalized_message.schema.json").read_text("utf-8"))
        nm_validator = jsonschema.Draft202012Validator(nm_schema)
        att_schema = json.loads((root / "schemas" / "attachment_artifact.schema.json").read_text("utf-8"))
        att_validator = jsonschema.Draft202012Validator(att_schema)

        expected_attachment_ids_by_msg = {}
        for p in (root / "data" / "samples" / "emails").glob("*.json"):
            nm = json.loads(p.read_text(encoding="utf-8"))
            expected_attachment_ids_by_msg[nm["message_id"]] = nm.get("attachment_ids", [])

        av_map = {}
        for meta_path in (root / "data" / "samples" / "attachments").glob("*.meta.json"):
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
            av_map[meta["sha256"]] = meta["av_status"]

        adapter = FilesystemMailIngestAdapter(
            raw_mime_dir=root / "data" / "samples" / "raw_mime",
            attachments_dir=root / "data" / "samples" / "attachments",
        )

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = FileRawStore(base_dir=base)
            audit_logger = FileAuditLogger(base_dir=base)
            attachment_stage = AttachmentStage(
                adapter=adapter,
                raw_store=store,
                derived_store=store,
                av_scanner=Sha256MappingAVScanner(av_map, default_status="FAILED"),
                attachments_out_dir=base / "attachments",
            )

            runner = IngestNormalizeRunner(
                adapter=adapter,
                ingestion_source="M365_GRAPH",
                raw_store=store,
                state_dir=base / "state",
                normalized_out_dir=base / "normalized",
                audit_logger=audit_logger,
                attachment_stage=attachment_stage,
            )

            produced = runner.run_once(limit=100)
            self.assertEqual(len(produced), 11)
            for nm in produced:
                nm_validator.validate(nm)
                self.assertEqual(
                    nm["attachment_ids"], expected_attachment_ids_by_msg.get(nm["message_id"], [])
                )

            artifact_paths = list((base / "attachments").glob("*.artifact.json"))
            self.assertEqual(len(artifact_paths), 5)
            artifacts = {p.stem.replace(".artifact", ""): json.loads(p.read_text("utf-8")) for p in artifact_paths}

            for a in artifacts.values():
                att_validator.validate(a)

            infected_id = "0c3eae85-c322-509b-879d-4bd24fc178b2"
            self.assertIn(infected_id, artifacts)
            infected = artifacts[infected_id]
            self.assertEqual(infected["av_status"], "INFECTED")
            self.assertIsNone(infected["extracted_text_uri"])
            self.assertIsNone(infected["extracted_text_sha256"])

            clean_id = "6e79ab40-7f41-5e07-95cb-0becfec38a4d"
            self.assertIn(clean_id, artifacts)
            clean = artifacts[clean_id]
            self.assertEqual(clean["av_status"], "CLEAN")
            self.assertIsNotNone(clean.get("extracted_text_uri"))
            self.assertIsNotNone(clean.get("extracted_text_sha256"))

            malware_msg_id = "b81451c0-5745-5dba-9d44-6b7e245335ff"
            audit_path = base / "audit" / malware_msg_id / f"{produced[0]['run_id']}.jsonl"
            # run_id is deterministic and stored in the normalized record for that message.
            run_id = next(nm["run_id"] for nm in produced if nm["message_id"] == malware_msg_id)
            audit_path = base / "audit" / malware_msg_id / f"{run_id}.jsonl"
            lines = [ln for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), 3)
            stages = [json.loads(ln)["stage"] for ln in lines]
            self.assertEqual(stages, ["INGEST", "NORMALIZE", "ATTACHMENTS"])


if __name__ == "__main__":
    unittest.main()

