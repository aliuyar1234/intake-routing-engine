import json
import tempfile
import unittest
from pathlib import Path

from ieim.audit.file_audit_log import FileAuditLogger
from ieim.hitl.service import HitlService
from ieim.pipeline.p7_hitl import HitlReviewItemsRunner
from ieim.raw_store import sha256_prefixed


class TestP7HitlWorkflow(unittest.TestCase):
    def test_review_items_and_corrections_are_audited(self) -> None:
        root = Path(__file__).resolve().parents[1]

        normalized_dir = root / "data" / "samples" / "emails"
        attachments_dir = root / "data" / "samples" / "attachments"
        gold_dir = root / "data" / "samples" / "gold"

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            hitl_dir = base / "hitl"
            drafts_dir = base / "drafts"
            drafts_dir.mkdir(parents=True, exist_ok=True)

            audit_logger = FileAuditLogger(base_dir=base)

            runner = HitlReviewItemsRunner(
                repo_root=root,
                normalized_dir=normalized_dir,
                attachments_dir=attachments_dir,
                identity_dir=gold_dir,
                classification_dir=gold_dir,
                extraction_dir=gold_dir,
                routing_dir=gold_dir,
                drafts_dir=drafts_dir,
                hitl_out_dir=hitl_dir,
                audit_logger=audit_logger,
            )

            produced = runner.run()
            produced_ids = {p["message_id"] for p in produced}
            self.assertTrue(
                {"b81451c0-5745-5dba-9d44-6b7e245335ff", "7fe5dd82-0527-5644-ac06-937c6f22562e"}.issubset(
                    produced_ids
                )
            )

            first = produced[0]
            review_item_path = Path(first["path"])
            self.assertTrue(review_item_path.exists())
            review_item = json.loads(review_item_path.read_text(encoding="utf-8"))

            svc = HitlService(repo_root=root, hitl_dir=hitl_dir, audit_logger=audit_logger)
            correction_path = svc.submit_correction(
                review_item_path=review_item_path,
                actor_id="reviewer@example.test",
                corrections=[
                    {
                        "target_stage": "ROUTE",
                        "patch": [
                            {
                                "op": "replace",
                                "path": "/queue_id",
                                "value": "QUEUE_INTAKE_REVIEW_GENERAL",
                            }
                        ],
                        "justification": "manual routing override for test",
                        "evidence": [],
                    }
                ],
                note="test correction",
            )
            self.assertTrue(correction_path.exists())

            message_id = str(review_item["message_id"])
            run_id = str(review_item["run_id"])
            audit_path = base / "audit" / message_id / f"{run_id}.jsonl"
            self.assertTrue(audit_path.exists())

            events = [json.loads(ln) for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertGreaterEqual(len(events), 2)

            last = events[-1]
            self.assertEqual(last["stage"], "HITL")
            self.assertEqual(last["actor_type"], "HUMAN")
            self.assertEqual(last["actor_id"], "reviewer@example.test")

            corr_bytes = correction_path.read_bytes()
            self.assertEqual(last["output_ref"]["sha256"], sha256_prefixed(corr_bytes))


if __name__ == "__main__":
    unittest.main()

