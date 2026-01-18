import json
import tempfile
import unittest
from dataclasses import replace
from pathlib import Path

from ieim.config import load_config
from ieim.llm.adapter import LLMAdapter
from ieim.llm.gating import should_call_llm_classify
from ieim.llm.mapping import LLMMappingError, build_classification_result_from_llm, merge_llm_extraction_into_result
from ieim.llm.providers import LLMProvider, ProviderResponse
from ieim.raw_store import sha256_prefixed


class _StubProvider(LLMProvider):
    def __init__(self, *, outputs: list[dict]) -> None:
        self.outputs = list(outputs)
        self.calls: list[dict] = []

    def chat_json(
        self,
        *,
        model: str,
        system_prompt: str,
        user_prompt: str,
        temperature: float,
        max_tokens: int,
    ) -> ProviderResponse:
        self.calls.append(
            {
                "model": model,
                "temperature": temperature,
                "max_tokens": max_tokens,
            }
        )
        out = self.outputs.pop(0)
        return ProviderResponse(content=json.dumps(out), usage=None)


class TestP4LLMAdapterUnit(unittest.TestCase):
    def test_llm_adapter_uses_cache(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cfg = load_config(path=root / "configs" / "prod.yaml")
        cfg = replace(cfg, classification=replace(cfg.classification, llm=replace(cfg.classification.llm, max_calls_per_day=10)))
        stub = _StubProvider(
            outputs=[
                {
                    "intents": [
                        {
                            "label": "INTENT_GENERAL_INQUIRY",
                            "confidence": 0.6,
                            "evidence_snippets": ["hello"],
                        }
                    ],
                    "primary_intent": "INTENT_GENERAL_INQUIRY",
                    "product_line": {
                        "label": "PROD_UNKNOWN",
                        "confidence": 0.5,
                        "evidence_snippets": ["hello"],
                    },
                    "urgency": {
                        "label": "URG_NORMAL",
                        "confidence": 0.6,
                        "evidence_snippets": ["hello"],
                    },
                    "risk_flags": [],
                }
            ]
        )

        nm = {
            "message_id": "00000000-0000-0000-0000-000000000001",
            "run_id": "00000000-0000-0000-0000-000000000002",
            "ingested_at": "2026-01-18T00:00:00Z",
            "language": "en",
            "subject_c14n": "hello",
            "body_text_c14n": "",
        }

        with tempfile.TemporaryDirectory() as td:
            adapter = LLMAdapter(repo_root=root, config=cfg, provider=stub, cache_dir=Path(td))
            r1 = adapter.classify(normalized_message=nm, message_fingerprint="sha256:" + "1" * 64)
            r2 = adapter.classify(normalized_message=nm, message_fingerprint="sha256:" + "1" * 64)

        self.assertFalse(r1.cache_hit)
        self.assertTrue(r2.cache_hit)
        self.assertEqual(len(stub.calls), 1)

    def test_llm_gate_allows_low_confidence_no_risk_flags(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cfg = load_config(path=root / "configs" / "prod.yaml")
        cfg = replace(
            cfg,
            classification=replace(
                cfg.classification,
                llm=replace(cfg.classification.llm, enabled=True, provider="openai"),
            ),
        )

        det = {"risk_flags": [], "primary_intent": {"confidence": 0.1}}
        gate = should_call_llm_classify(config=cfg, deterministic_classification=det)
        self.assertTrue(gate.allowed)

    def test_llm_mapping_rejects_non_canonical_label(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cfg = load_config(path=root / "configs" / "prod.yaml")

        nm = {
            "message_id": "00000000-0000-0000-0000-000000000003",
            "run_id": "00000000-0000-0000-0000-000000000004",
            "ingested_at": "2026-01-18T00:00:00Z",
            "subject_c14n": "hello",
            "body_text_c14n": "hello",
            "message_fingerprint": "sha256:" + "2" * 64,
            "raw_mime_sha256": "sha256:" + "3" * 64,
        }

        with self.assertRaises(LLMMappingError):
            build_classification_result_from_llm(
                config=cfg,
                normalized_message=nm,
                llm_output={
                    "intents": [
                        {
                            "label": "INTENT_NOT_REAL",
                            "confidence": 0.9,
                            "evidence_snippets": ["hello"],
                        }
                    ],
                    "primary_intent": "INTENT_NOT_REAL",
                    "product_line": {
                        "label": "PROD_UNKNOWN",
                        "confidence": 0.5,
                        "evidence_snippets": ["hello"],
                    },
                    "urgency": {
                        "label": "URG_NORMAL",
                        "confidence": 0.6,
                        "evidence_snippets": ["hello"],
                    },
                    "risk_flags": [],
                },
                llm_model_info={
                    "provider": "openai",
                    "model_name": "x",
                    "model_version": "pinned",
                    "prompt_version": "1.0.0",
                    "prompt_sha256": "sha256:" + "0" * 64,
                    "temperature": 0.0,
                    "max_tokens": 1,
                },
                deterministic_risk_flags=[],
            )

    def test_llm_extraction_merge_adds_policy_number(self) -> None:
        root = Path(__file__).resolve().parents[1]
        cfg = load_config(path=root / "configs" / "prod.yaml")

        base = {"message_id": "m", "run_id": "r", "entities": [], "created_at": "2026-01-18T00:00:00Z"}
        llm_out = {
            "entities": [
                {
                    "entity_type": "ENT_POLICY_NUMBER",
                    "value_redacted": "12-1234567",
                    "confidence": 0.9,
                    "evidence_snippets": ["12-1234567"],
                }
            ]
        }
        merged = merge_llm_extraction_into_result(
            config=cfg,
            extraction_result=base,
            llm_output=llm_out,
            subject_redacted="policy 12-1234567",
            body_redacted="",
        )
        self.assertEqual(len(merged["entities"]), 1)
        ent = merged["entities"][0]
        self.assertEqual(ent["entity_type"], "ENT_POLICY_NUMBER")
        self.assertEqual(ent["value"], "12-1234567")
        self.assertEqual(ent["value_sha256"], sha256_prefixed(b"12-1234567"))


if __name__ == "__main__":
    unittest.main()
