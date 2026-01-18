from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

import jsonschema


@dataclass(frozen=True)
class LLMContract:
    name: str
    version: str
    schema: dict[str, Any]


def _contract_classify_v1() -> LLMContract:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["intents", "primary_intent", "product_line", "urgency", "risk_flags"],
        "properties": {
            "intents": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "confidence", "evidence_snippets"],
                    "properties": {
                        "label": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "evidence_snippets": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 200},
                        },
                    },
                },
            },
            "primary_intent": {"type": "string"},
            "product_line": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "confidence", "evidence_snippets"],
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "evidence_snippets": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 200},
                    },
                },
            },
            "urgency": {
                "type": "object",
                "additionalProperties": False,
                "required": ["label", "confidence", "evidence_snippets"],
                "properties": {
                    "label": {"type": "string"},
                    "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                    "evidence_snippets": {
                        "type": "array",
                        "items": {"type": "string", "maxLength": 200},
                    },
                },
            },
            "risk_flags": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["label", "confidence", "evidence_snippets"],
                    "properties": {
                        "label": {"type": "string"},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "evidence_snippets": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 200},
                        },
                    },
                },
            },
        },
    }
    return LLMContract(name="ClassifyLLMOutput", version="1.0.0", schema=schema)


def _contract_extract_v1() -> LLMContract:
    schema: dict[str, Any] = {
        "type": "object",
        "additionalProperties": False,
        "required": ["entities"],
        "properties": {
            "entities": {
                "type": "array",
                "items": {
                    "type": "object",
                    "additionalProperties": False,
                    "required": ["entity_type", "value_redacted", "confidence", "evidence_snippets"],
                    "properties": {
                        "entity_type": {"type": "string"},
                        "value_redacted": {"type": "string", "maxLength": 200},
                        "confidence": {"type": "number", "minimum": 0.0, "maximum": 1.0},
                        "evidence_snippets": {
                            "type": "array",
                            "items": {"type": "string", "maxLength": 200},
                        },
                    },
                },
            }
        },
    }
    return LLMContract(name="ExtractLLMOutput", version="1.0.0", schema=schema)


@lru_cache(maxsize=8)
def get_contract(*, name: str, version: str) -> LLMContract:
    if name == "ClassifyLLMOutput" and version == "1.0.0":
        return _contract_classify_v1()
    if name == "ExtractLLMOutput" and version == "1.0.0":
        return _contract_extract_v1()
    raise ValueError(f"unsupported LLM contract: {name} v{version}")


@lru_cache(maxsize=8)
def _validator_cache(name: str, version: str) -> jsonschema.Draft202012Validator:
    contract = get_contract(name=name, version=version)
    return jsonschema.Draft202012Validator(contract.schema)


def validate_contract_output(*, name: str, version: str, output: Any) -> None:
    _validator_cache(name, version).validate(output)


def sha256_prompt_file(*, repo_root: Path, relative_path: str) -> str:
    from ieim.raw_store import sha256_prefixed

    path = (repo_root / relative_path).resolve()
    data = path.read_bytes()
    return sha256_prefixed(data)


def sha256_prompt_pair(*, system_prompt: bytes, task_prompt: bytes) -> str:
    from ieim.raw_store import sha256_prefixed

    data = system_prompt + b"\n" + task_prompt
    return sha256_prefixed(data)


def load_prompt_json(*, repo_root: Path, relative_path: str) -> dict[str, Any]:
    path = (repo_root / relative_path).resolve()
    return json.loads(path.read_text(encoding="utf-8"))

