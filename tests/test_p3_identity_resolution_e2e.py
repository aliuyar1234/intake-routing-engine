import json
import tempfile
import unittest
from pathlib import Path

import jsonschema

from ieim.audit.file_audit_log import FileAuditLogger
from ieim.identity.adapters import InMemoryCRMAdapter, InMemoryClaimsAdapter, InMemoryPolicyAdapter
from ieim.pipeline.p3_identity_resolution import IdentityResolutionRunner


class TestP3IdentityResolutionE2E(unittest.TestCase):
    def _event_hash(self, event: dict) -> str:
        event_no_hash = {k: v for k, v in event.items() if k != "event_hash"}
        encoded = json.dumps(
            event_no_hash, sort_keys=True, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        import hashlib

        return "sha256:" + hashlib.sha256(encoded).hexdigest()

    def test_identity_regression_against_gold_and_audit(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schema = json.loads(
            (root / "schemas" / "identity_resolution_result.schema.json").read_text("utf-8")
        )
        validator = jsonschema.Draft202012Validator(schema)
        audit_schema = json.loads((root / "schemas" / "audit_event.schema.json").read_text("utf-8"))
        audit_validator = jsonschema.Draft202012Validator(audit_schema)

        crm = InMemoryCRMAdapter({"kunde1@example.test": ["45-1234567"]})

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            audit_logger = FileAuditLogger(base_dir=base)
            runner = IdentityResolutionRunner(
                repo_root=root,
                normalized_dir=root / "data" / "samples" / "emails",
                attachments_dir=root / "data" / "samples" / "attachments",
                identity_out_dir=base / "identity",
                drafts_out_dir=base / "drafts",
                policy_adapter=InMemoryPolicyAdapter(),
                claims_adapter=InMemoryClaimsAdapter(),
                crm_adapter=crm,
                audit_logger=audit_logger,
                config_path_override=root / "configs" / "test_baseline.yaml",
            )

            produced = runner.run()
            self.assertEqual(len(produced), 11)

            for res in produced:
                validator.validate(res)
                gold = json.loads(
                    (root / "data" / "samples" / "gold" / f"{res['message_id']}.identity.json").read_text(
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
                self.assertEqual(event["stage"], "IDENTITY")
                self.assertEqual(event["decision_hash"], res["decision_hash"])
                self.assertEqual(event["event_hash"], self._event_hash(event))

            drafts = list((base / "drafts").glob("*.request_info.md"))
            self.assertEqual(len(drafts), 7)

            de_template = (root / "configs" / "templates" / "request_info_de.md").read_text(
                encoding="utf-8"
            )
            en_template = (root / "configs" / "templates" / "request_info_en.md").read_text(
                encoding="utf-8"
            )

            de_draft = (base / "drafts" / "101f1b6d-ea7b-54b4-833d-53e11c190174.request_info.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(de_draft, de_template)

            es_draft = (base / "drafts" / "7fe5dd82-0527-5644-ac06-937c6f22562e.request_info.md").read_text(
                encoding="utf-8"
            )
            self.assertEqual(es_draft, en_template)


if __name__ == "__main__":
    unittest.main()
