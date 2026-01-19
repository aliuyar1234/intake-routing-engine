import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from ieim.audit.file_audit_log import FileAuditLogger
from ieim.pipeline.p4_classify_extract import ClassifyExtractRunner


class TestP4ClassifyExtractE2E(unittest.TestCase):
    def _event_hash(self, event: dict) -> str:
        event_no_hash = {k: v for k, v in event.items() if k != "event_hash"}
        encoded = json.dumps(
            event_no_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        import hashlib

        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def test_classify_extract_regression_against_gold_and_audit(self) -> None:
        root = Path(__file__).resolve().parents[1]

        classification_schema = json.loads(
            (root / "schemas" / "classification_result.schema.json").read_text("utf-8")
        )
        extraction_schema = json.loads(
            (root / "schemas" / "extraction_result.schema.json").read_text("utf-8")
        )
        audit_schema = json.loads((root / "schemas" / "audit_event.schema.json").read_text("utf-8"))

        classification_validator = jsonschema.Draft202012Validator(classification_schema)
        extraction_validator = jsonschema.Draft202012Validator(extraction_schema)
        audit_validator = jsonschema.Draft202012Validator(audit_schema)

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            audit_logger = FileAuditLogger(base_dir=base)
            runner = ClassifyExtractRunner(
                repo_root=root,
                normalized_dir=root / "data" / "samples" / "emails",
                attachments_dir=root / "data" / "samples" / "attachments",
                classification_out_dir=base / "classification",
                extraction_out_dir=base / "extraction",
                audit_logger=audit_logger,
                config_path_override=root / "configs" / "test_baseline.yaml",
            )

            produced = runner.run()
            self.assertEqual(len(produced), 11)

            for cls, ex in produced:
                classification_validator.validate(cls)
                extraction_validator.validate(ex)

                gold_cls = json.loads(
                    (root / "data" / "samples" / "gold" / f"{cls['message_id']}.classification.json").read_text(
                        encoding="utf-8"
                    )
                )
                gold_ex = json.loads(
                    (root / "data" / "samples" / "gold" / f"{ex['message_id']}.extraction.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(cls, gold_cls)
                self.assertEqual(ex, gold_ex)

                audit_path = base / "audit" / cls["message_id"] / f"{cls['run_id']}.jsonl"
                self.assertTrue(audit_path.exists())
                lines = [ln for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
                self.assertEqual(len(lines), 2)
                ev1 = json.loads(lines[0])
                ev2 = json.loads(lines[1])

                audit_validator.validate(ev1)
                audit_validator.validate(ev2)

                self.assertEqual(ev1["stage"], "CLASSIFY")
                self.assertEqual(ev1["decision_hash"], cls["decision_hash"])
                self.assertEqual(ev1["event_hash"], self._event_hash(ev1))

                self.assertEqual(ev2["stage"], "EXTRACT")
                self.assertIsNone(ev2["decision_hash"])
                self.assertEqual(ev2["event_hash"], self._event_hash(ev2))


if __name__ == "__main__":
    unittest.main()
