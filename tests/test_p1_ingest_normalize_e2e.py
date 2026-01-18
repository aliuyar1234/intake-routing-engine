import json
import hashlib
import tempfile
import unittest
from pathlib import Path

import jsonschema

from ieim.audit.file_audit_log import FileAuditLogger
from ieim.ingest.filesystem_adapter import FilesystemMailIngestAdapter
from ieim.pipeline.p1_ingest_normalize import IngestNormalizeRunner
from ieim.raw_store import FileRawStore


class TestP1IngestNormalizeE2E(unittest.TestCase):
    def _event_hash(self, event: dict) -> str:
        event_no_hash = {k: v for k, v in event.items() if k != "event_hash"}
        encoded = json.dumps(
            event_no_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def test_ingest_to_raw_store_to_normalize_and_dedupe(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "schemas" / "normalized_message.schema.json").read_text("utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        audit_schema = json.loads((root / "schemas" / "audit_event.schema.json").read_text("utf-8"))
        audit_validator = jsonschema.Draft202012Validator(audit_schema)

        adapter = FilesystemMailIngestAdapter(
            raw_mime_dir=root / "data" / "samples" / "raw_mime",
            attachments_dir=root / "data" / "samples" / "attachments",
        )

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = FileRawStore(base_dir=base)
            audit_logger = FileAuditLogger(base_dir=base)
            runner = IngestNormalizeRunner(
                adapter=adapter,
                ingestion_source="M365_GRAPH",
                raw_store=store,
                state_dir=base / "state",
                normalized_out_dir=base / "normalized",
                audit_logger=audit_logger,
            )

            produced = runner.run_once(limit=100)
            self.assertEqual(len(produced), 11)
            for nm in produced:
                validator.validate(nm)
                audit_path = base / "audit" / nm["message_id"] / f"{nm['run_id']}.jsonl"
                self.assertTrue(audit_path.exists())
                lines = [
                    ln
                    for ln in audit_path.read_text(encoding="utf-8").splitlines()
                    if ln.strip()
                ]
                self.assertEqual(len(lines), 2)
                events = [json.loads(ln) for ln in lines]
                for e in events:
                    audit_validator.validate(e)
                    self.assertEqual(e["message_id"], nm["message_id"])
                    self.assertEqual(e["run_id"], nm["run_id"])
                    self.assertEqual(e["event_hash"], self._event_hash(e))
                self.assertIsNone(events[0]["prev_event_hash"])
                self.assertEqual(events[1]["prev_event_hash"], events[0]["event_hash"])
                self.assertEqual(
                    [events[0]["stage"], events[1]["stage"]], ["INGEST", "NORMALIZE"]
                )

            produced2 = runner.run_once(limit=100)
            self.assertEqual(produced2, [])

            cursor_path = base / "state" / "ingest_cursor.json"
            cursor_path.write_text(json.dumps({"cursor": None}) + "\n", encoding="utf-8")

            produced3 = runner.run_once(limit=100)
            self.assertEqual(produced3, [])

            files = list((base / "normalized").glob("*.json"))
            self.assertEqual(len(files), 11)


if __name__ == "__main__":
    unittest.main()
