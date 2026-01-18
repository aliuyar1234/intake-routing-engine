import json
import tempfile
import unittest
from pathlib import Path

from ieim.config import load_config
from ieim.llm.gating import should_call_llm_classify
from ieim.route.evaluator import evaluate_routing


class TestP8IncidentToggles(unittest.TestCase):
    def test_force_review_overrides_routing(self) -> None:
        root = Path(__file__).resolve().parents[1]
        nm = json.loads(
            (root / "data" / "samples" / "emails" / "101f1b6d-ea7b-54b4-833d-53e11c190174.json").read_text(
                encoding="utf-8"
            )
        )
        identity = json.loads(
            (root / "data" / "samples" / "gold" / "101f1b6d-ea7b-54b4-833d-53e11c190174.identity.json").read_text(
                encoding="utf-8"
            )
        )
        cls = json.loads(
            (
                root
                / "data"
                / "samples"
                / "gold"
                / "101f1b6d-ea7b-54b4-833d-53e11c190174.classification.json"
            ).read_text(encoding="utf-8")
        )

        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "cfg.yaml"
            cfg_path.write_text(
                "\n".join(
                    [
                        "pack:",
                        "  system_id: IEIM",
                        '  canonical_spec_semver: "1.0.1"',
                        "",
                        "runtime:",
                        "  determinism_mode: false",
                        "  supported_languages: [de, en]",
                        "",
                        "incident:",
                        "  force_review: true",
                        '  force_review_queue_id: "QUEUE_INTAKE_REVIEW_GENERAL"',
                        "  disable_llm: false",
                        "  block_case_create_risk_flags_any: []",
                        "",
                        "classification:",
                        "  min_confidence_for_auto: 0.80",
                        '  rules_version: "1.0.0"',
                        "  llm:",
                        "    enabled: false",
                        '    provider: "disabled"',
                        '    model_name: "disabled"',
                        '    model_version: "disabled"',
                        "    prompt_versions: { classify: \"1.0.0\", extract: \"1.0.0\" }",
                        "    token_budgets: { classify: 10, extract: 10 }",
                        "    max_calls_per_day: 0",
                        "",
                        "extraction:",
                        "  iban_policy: { enabled: true, store_mode: \"HASH_ONLY\" }",
                        "",
                        "routing:",
                        '  ruleset_path: "configs/routing_tables/routing_rules_v1.4.1.json"',
                        '  ruleset_version: "1.4.1"',
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            cfg = load_config(path=cfg_path)
            out = evaluate_routing(
                repo_root=root,
                config=cfg,
                normalized_message=nm,
                identity_result=identity,
                classification_result=cls,
            ).decision

            self.assertEqual(out["queue_id"], "QUEUE_INTAKE_REVIEW_GENERAL")
            self.assertEqual(out["rule_id"], "INCIDENT_FORCE_REVIEW")
            self.assertTrue(out["fail_closed"])
            self.assertEqual(out["fail_closed_reason"], "INCIDENT_FORCE_REVIEW")
            self.assertEqual(out["actions"], ["ATTACH_ORIGINAL_EMAIL"])

    def test_block_case_create_for_risk_flags(self) -> None:
        root = Path(__file__).resolve().parents[1]
        nm = json.loads(
            (root / "data" / "samples" / "emails" / "101f1b6d-ea7b-54b4-833d-53e11c190174.json").read_text(
                encoding="utf-8"
            )
        )
        identity = json.loads(
            (root / "data" / "samples" / "gold" / "101f1b6d-ea7b-54b4-833d-53e11c190174.identity.json").read_text(
                encoding="utf-8"
            )
        )
        cls = json.loads(
            (
                root
                / "data"
                / "samples"
                / "gold"
                / "101f1b6d-ea7b-54b4-833d-53e11c190174.classification.json"
            ).read_text(encoding="utf-8")
        )
        cls["risk_flags"] = [{"label": "RISK_LEGAL_THREAT", "confidence": 1.0, "evidence": []}]

        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "cfg.yaml"
            cfg_path.write_text(
                "\n".join(
                    [
                        "pack:",
                        "  system_id: IEIM",
                        '  canonical_spec_semver: "1.0.1"',
                        "",
                        "runtime:",
                        "  determinism_mode: false",
                        "  supported_languages: [de, en]",
                        "",
                        "incident:",
                        "  force_review: false",
                        '  force_review_queue_id: "QUEUE_INTAKE_REVIEW_GENERAL"',
                        "  disable_llm: false",
                        "  block_case_create_risk_flags_any: [RISK_LEGAL_THREAT]",
                        "",
                        "classification:",
                        "  min_confidence_for_auto: 0.80",
                        '  rules_version: "1.0.0"',
                        "  llm:",
                        "    enabled: false",
                        '    provider: "disabled"',
                        '    model_name: "disabled"',
                        '    model_version: "disabled"',
                        "    prompt_versions: { classify: \"1.0.0\", extract: \"1.0.0\" }",
                        "    token_budgets: { classify: 10, extract: 10 }",
                        "    max_calls_per_day: 0",
                        "",
                        "extraction:",
                        "  iban_policy: { enabled: true, store_mode: \"HASH_ONLY\" }",
                        "",
                        "routing:",
                        '  ruleset_path: "configs/routing_tables/routing_rules_v1.4.1.json"',
                        '  ruleset_version: "1.4.1"',
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            cfg = load_config(path=cfg_path)
            out = evaluate_routing(
                repo_root=root,
                config=cfg,
                normalized_message=nm,
                identity_result=identity,
                classification_result=cls,
            ).decision

            self.assertIn("BLOCK_CASE_CREATE", out["actions"])
            self.assertNotIn("CREATE_CASE", out["actions"])
            self.assertTrue(out["fail_closed"])
            self.assertEqual(out["fail_closed_reason"], "INCIDENT_BLOCK_CASE_CREATE")

    def test_disable_llm_toggle_blocks_llm_gate(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            cfg_path = Path(td) / "cfg.yaml"
            cfg_path.write_text(
                "\n".join(
                    [
                        "pack:",
                        "  system_id: IEIM",
                        '  canonical_spec_semver: "1.0.1"',
                        "",
                        "runtime:",
                        "  determinism_mode: false",
                        "  supported_languages: [de, en]",
                        "",
                        "incident:",
                        "  force_review: false",
                        '  force_review_queue_id: "QUEUE_INTAKE_REVIEW_GENERAL"',
                        "  disable_llm: true",
                        "  block_case_create_risk_flags_any: []",
                        "",
                        "classification:",
                        "  min_confidence_for_auto: 0.80",
                        '  rules_version: "1.0.0"',
                        "  llm:",
                        "    enabled: true",
                        '    provider: "openai"',
                        '    model_name: "gpt-4.1"',
                        '    model_version: "pinned"',
                        "    prompt_versions: { classify: \"1.0.0\", extract: \"1.0.0\" }",
                        "    token_budgets: { classify: 10, extract: 10 }",
                        "    max_calls_per_day: 1",
                        "",
                        "extraction:",
                        "  iban_policy: { enabled: true, store_mode: \"HASH_ONLY\" }",
                        "",
                        "routing:",
                        '  ruleset_path: "configs/routing_tables/routing_rules_v1.4.1.json"',
                        '  ruleset_version: "1.4.1"',
                        "",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )

            cfg = load_config(path=cfg_path)
            gate = should_call_llm_classify(
                config=cfg,
                deterministic_classification={
                    "risk_flags": [],
                    "primary_intent": {"label": "INTENT_GENERAL_INQUIRY", "confidence": 0.0, "evidence": []},
                },
            )
            self.assertFalse(gate.allowed)
            self.assertEqual(gate.reason, "INCIDENT_DISABLE_LLM")


if __name__ == "__main__":
    unittest.main()

