import json
import unittest
from pathlib import Path

from ieim.config import load_config
from ieim.route.evaluator import evaluate_routing


class TestP5RoutingUnit(unittest.TestCase):
    def test_override_precedence_malware_over_gdpr(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cfg = load_config(path=root / "configs" / "prod.yaml")

        nm = {
            "message_id": "msg-1",
            "run_id": "run-1",
            "ingested_at": "2026-01-01T00:00:00Z",
            "message_fingerprint": "sha256:" + ("1" * 64),
            "raw_mime_sha256": "sha256:" + ("2" * 64),
        }
        identity = {"status": "IDENTITY_CONFIRMED"}
        classification = {
            "primary_intent": {"label": "INTENT_GDPR_REQUEST"},
            "product_line": {"label": "PROD_UNKNOWN"},
            "urgency": {"label": "URG_NORMAL"},
            "risk_flags": [{"label": "RISK_SECURITY_MALWARE"}],
        }

        out = evaluate_routing(
            repo_root=root, config=cfg, normalized_message=nm, identity_result=identity, classification_result=classification
        ).decision
        self.assertEqual(out["rule_id"], "ROUTE_SECURITY_MALWARE")
        self.assertEqual(out["queue_id"], "QUEUE_SECURITY_REVIEW")
        self.assertTrue(out["fail_closed"])

    def test_no_rule_match_fails_closed_to_general_review(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cfg = load_config(path=root / "configs" / "prod.yaml")

        nm = {
            "message_id": "msg-2",
            "run_id": "run-2",
            "ingested_at": "2026-01-01T00:00:00Z",
            "message_fingerprint": "sha256:" + ("3" * 64),
            "raw_mime_sha256": "sha256:" + ("4" * 64),
        }
        identity = {"status": "IDENTITY_CONFIRMED"}
        classification = {
            "primary_intent": {"label": "INTENT_GENERAL_INQUIRY"},
            "product_line": {"label": "PROD_LIFE"},
            "urgency": {"label": "URG_NORMAL"},
            "risk_flags": [],
        }

        out = evaluate_routing(
            repo_root=root, config=cfg, normalized_message=nm, identity_result=identity, classification_result=classification
        ).decision
        self.assertEqual(out["queue_id"], "QUEUE_INTAKE_REVIEW_GENERAL")
        self.assertTrue(out["fail_closed"])
        self.assertEqual(out["fail_closed_reason"], "NO_RULE_MATCH")


if __name__ == "__main__":
    unittest.main()

