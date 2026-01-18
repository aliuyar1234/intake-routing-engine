import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from ieim.audit.file_audit_log import FileAuditLogger
from ieim.pipeline.p5_routing import RoutingRunner


class TestP5RoutingE2E(unittest.TestCase):
    def _event_hash(self, event: dict) -> str:
        event_no_hash = {k: v for k, v in event.items() if k != "event_hash"}
        encoded = json.dumps(
            event_no_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        import hashlib

        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def test_routing_regression_against_gold_and_audit(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schema = json.loads((root / "schemas" / "routing_decision.schema.json").read_text("utf-8"))
        validator = jsonschema.Draft202012Validator(schema)
        audit_schema = json.loads((root / "schemas" / "audit_event.schema.json").read_text("utf-8"))
        audit_validator = jsonschema.Draft202012Validator(audit_schema)

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            audit_logger = FileAuditLogger(base_dir=base)
            runner = RoutingRunner(
                repo_root=root,
                normalized_dir=root / "data" / "samples" / "emails",
                identity_dir=root / "data" / "samples" / "gold",
                classification_dir=root / "data" / "samples" / "gold",
                routing_out_dir=base / "routing",
                audit_logger=audit_logger,
            )

            produced = runner.run()
            self.assertEqual(len(produced), 11)

            for res in produced:
                validator.validate(res)
                gold = json.loads(
                    (root / "data" / "samples" / "gold" / f"{res['message_id']}.routing.json").read_text(
                        encoding="utf-8"
                    )
                )
                self.assertEqual(res, gold)

                audit_path = base / "audit" / res["message_id"] / f"{res['run_id']}.jsonl"
                self.assertTrue(audit_path.exists())
                lines = [ln for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
                self.assertEqual(len(lines), 1)
                event = json.loads(lines[0])
                audit_validator.validate(event)
                self.assertEqual(event["stage"], "ROUTE")
                self.assertEqual(event["decision_hash"], res["decision_hash"])
                self.assertEqual(event["event_hash"], self._event_hash(event))


if __name__ == "__main__":
    unittest.main()

