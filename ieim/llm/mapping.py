from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

from ieim.classify.classifier import _classification_schema_id_and_version, _primary_intent_priority
from ieim.config import IEIMConfig
from ieim.determinism.decision_hash import decision_hash
from ieim.llm.canonical_labels import load_canonical_label_sets
from ieim.llm.redaction import redact_preserve_length
from ieim.raw_store import sha256_prefixed


class LLMMappingError(ValueError):
    pass


def _snippet_sha256(snippet: str) -> str:
    return sha256_prefixed(snippet.encode("utf-8"))


def _evidence_span(*, source: str, start: int, end: int, text: str) -> dict:
    snippet = text[start:end]
    return {
        "source": source,
        "start": int(start),
        "end": int(end),
        "snippet_redacted": snippet,
        "snippet_sha256": _snippet_sha256(snippet),
    }


def _find_span_from_snippet(*, snippet: str, subject: str, body: str) -> dict:
    needle = snippet.strip().lower()
    if not needle:
        raise LLMMappingError("empty evidence snippet")

    idx = subject.find(needle)
    if idx != -1:
        return _evidence_span(source="SUBJECT_C14N", start=idx, end=idx + len(needle), text=subject)

    idx = body.find(needle)
    if idx != -1:
        return _evidence_span(source="BODY_C14N", start=idx, end=idx + len(needle), text=body)

    raise LLMMappingError("evidence snippet not found in redacted canonical text")


def _require_non_empty_str(value: Any, *, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise LLMMappingError(f"{path} must be a non-empty string")
    return value


def _require_list(value: Any, *, path: str) -> list:
    if not isinstance(value, list):
        raise LLMMappingError(f"{path} must be a list")
    return value


def _ensure_labels_in_set(*, values: list[str], allowed: frozenset[str], path: str) -> None:
    for v in values:
        if v not in allowed:
            raise LLMMappingError(f"{path} contains non-canonical label: {v}")


def _map_labeled_items(
    *, items: list[dict[str, Any]], subject_redacted: str, body_redacted: str, allowed_labels: frozenset[str], path: str
) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for idx, it in enumerate(items):
        if not isinstance(it, dict):
            raise LLMMappingError(f"{path}[{idx}] must be an object")
        label = _require_non_empty_str(it.get("label"), path=f"{path}[{idx}].label")
        if label not in allowed_labels:
            raise LLMMappingError(f"{path}[{idx}].label not canonical: {label}")
        confidence = float(it.get("confidence") or 0.0)
        snippets = _require_list(it.get("evidence_snippets"), path=f"{path}[{idx}].evidence_snippets")
        if not snippets:
            raise LLMMappingError(f"{path}[{idx}].evidence_snippets must not be empty")
        evidence = [
            _find_span_from_snippet(
                snippet=_require_non_empty_str(s, path=f"{path}[{idx}].evidence_snippets[*]"),
                subject=subject_redacted,
                body=body_redacted,
            )
            for s in snippets
        ]
        out.append({"label": label, "confidence": confidence, "evidence": evidence})
    return out


def _map_labeled_single(
    *, obj: dict[str, Any], subject_redacted: str, body_redacted: str, allowed_labels: frozenset[str], path: str
) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise LLMMappingError(f"{path} must be an object")
    label = _require_non_empty_str(obj.get("label"), path=f"{path}.label")
    if label not in allowed_labels:
        raise LLMMappingError(f"{path}.label not canonical: {label}")
    confidence = float(obj.get("confidence") or 0.0)
    snippets = _require_list(obj.get("evidence_snippets"), path=f"{path}.evidence_snippets")
    if not snippets:
        raise LLMMappingError(f"{path}.evidence_snippets must not be empty")
    evidence = [
        _find_span_from_snippet(
            snippet=_require_non_empty_str(s, path=f"{path}.evidence_snippets[*]"),
            subject=subject_redacted,
            body=body_redacted,
        )
        for s in snippets
    ]
    return {"label": label, "confidence": confidence, "evidence": evidence}


def _pick_primary_intent(*, intents: list[dict[str, Any]]) -> dict[str, Any]:
    prio = _primary_intent_priority()
    return sorted(intents, key=lambda x: prio.get(str(x.get("label") or ""), 10_000))[0]


def _decision_hash_for_classification(
    *,
    config: IEIMConfig,
    normalized_message: dict,
    intents: list[dict],
    primary_intent: dict,
    product_line: dict,
    urgency: dict,
    risk_flags: list[dict],
) -> str:
    decision_input = {
        "system_id": config.system_id,
        "canonical_spec_semver": config.canonical_spec_semver,
        "stage": "CLASSIFY",
        "message_fingerprint": str(normalized_message.get("message_fingerprint") or ""),
        "raw_mime_sha256": str(normalized_message.get("raw_mime_sha256") or ""),
        "config_ref": {
            "config_path": config.config_path,
            "config_sha256": config.config_sha256,
        },
        "determinism_mode": config.determinism_mode,
        "llm": {
            "enabled": config.classification.llm.enabled,
            "provider": config.classification.llm.provider,
            "model_name": config.classification.llm.model_name,
            "model_version": config.classification.llm.model_version,
            "prompt_versions": config.classification.llm.prompt_versions,
        },
        "decision": {
            "intents": [
                {
                    "label": i["label"],
                    "confidence": i["confidence"],
                    "evidence": [
                        {
                            "source": e["source"],
                            "start": e["start"],
                            "end": e["end"],
                            "snippet_sha256": e["snippet_sha256"],
                        }
                        for e in i.get("evidence", [])
                    ],
                }
                for i in intents
            ],
            "primary_intent": {
                "label": primary_intent["label"],
                "confidence": primary_intent["confidence"],
            },
            "product_line": product_line["label"],
            "urgency": urgency["label"],
            "risk_flags": [
                {
                    "label": r["label"],
                    "confidence": r["confidence"],
                    "evidence": [
                        {
                            "source": e["source"],
                            "start": e["start"],
                            "end": e["end"],
                            "snippet_sha256": e["snippet_sha256"],
                        }
                        for e in r.get("evidence", [])
                    ],
                }
                for r in risk_flags
            ],
            "rules_version": config.classification.rules_version,
            "min_confidence_for_auto": config.classification.min_confidence_for_auto,
        },
    }
    return decision_hash(decision_input)


@dataclass(frozen=True)
class LLMClassificationMappingResult:
    classification_result: dict[str, Any]
    subject_redacted: str
    body_redacted: str


def build_classification_result_from_llm(
    *,
    config: IEIMConfig,
    normalized_message: dict,
    llm_output: dict[str, Any],
    llm_model_info: dict[str, Any],
    deterministic_risk_flags: list[dict],
) -> LLMClassificationMappingResult:
    schema_id, schema_version = _classification_schema_id_and_version()

    subject_redacted = redact_preserve_length(str(normalized_message.get("subject_c14n") or ""))
    body_redacted = redact_preserve_length(str(normalized_message.get("body_text_c14n") or ""))

    sets = load_canonical_label_sets()

    intents_raw = _require_list(llm_output.get("intents"), path="llm.intents")
    intents = _map_labeled_items(
        items=intents_raw,
        subject_redacted=subject_redacted,
        body_redacted=body_redacted,
        allowed_labels=sets["INTENT"],
        path="llm.intents",
    )

    if not intents:
        raise LLMMappingError("llm.intents must not be empty")

    product_line = _map_labeled_single(
        obj=llm_output.get("product_line"),
        subject_redacted=subject_redacted,
        body_redacted=body_redacted,
        allowed_labels=sets["PROD"],
        path="llm.product_line",
    )
    urgency = _map_labeled_single(
        obj=llm_output.get("urgency"),
        subject_redacted=subject_redacted,
        body_redacted=body_redacted,
        allowed_labels=sets["URG"],
        path="llm.urgency",
    )

    primary = _pick_primary_intent(intents=intents)

    risk_flags: list[dict] = []
    for r in deterministic_risk_flags:
        if isinstance(r, dict):
            risk_flags.append(r)

    decision_hash_value = _decision_hash_for_classification(
        config=config,
        normalized_message=normalized_message,
        intents=intents,
        primary_intent=primary,
        product_line=product_line,
        urgency=urgency,
        risk_flags=risk_flags,
    )

    result = {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "message_id": str(normalized_message["message_id"]),
        "run_id": str(normalized_message["run_id"]),
        "intents": intents,
        "primary_intent": primary,
        "product_line": product_line,
        "urgency": urgency,
        "risk_flags": risk_flags,
        "model_info": llm_model_info,
        "created_at": str(normalized_message["ingested_at"]),
        "decision_hash": decision_hash_value,
    }
    return LLMClassificationMappingResult(
        classification_result=result,
        subject_redacted=subject_redacted,
        body_redacted=body_redacted,
    )


_POLICY_NUMBER_RE = re.compile(r"\b(?P<num>\d{2}-\d{7})\b")
_CLAIM_NUMBER_RE = re.compile(r"\b(?P<clm>clm-\d{4}-\d{4})\b", re.IGNORECASE)
_DATE_RE = re.compile(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b")
_IBAN_RE = re.compile(r"\b(?P<iban>[A-Z]{2}\d{2}[A-Z0-9]{10,30})\b", re.IGNORECASE)


def _iban_redact(value: str) -> str:
    v = value.strip()
    if len(v) <= 8:
        return v
    return v[:4].lower() + "\u2026" + v[-4:].lower()


def _first_value_match(*, entity_type: str, text: str) -> Optional[str]:
    if entity_type == "ENT_POLICY_NUMBER":
        m = _POLICY_NUMBER_RE.search(text)
        return m.group("num") if m else None
    if entity_type == "ENT_CLAIM_NUMBER":
        m = _CLAIM_NUMBER_RE.search(text)
        return m.group("clm").upper() if m else None
    if entity_type == "ENT_DATE":
        m = _DATE_RE.search(text)
        return m.group("date") if m else None
    if entity_type == "ENT_IBAN":
        m = _IBAN_RE.search(text)
        return m.group("iban").upper() if m else None
    return None


def _provenance_for_value(*, value: str, subject: str, body: str) -> Optional[dict]:
    needle = value.lower()
    idx = subject.find(needle)
    if idx != -1:
        return {
            "source": "SUBJECT_C14N",
            "start": idx,
            "end": idx + len(needle),
            "snippet_redacted": subject[idx : idx + len(needle)],
            "snippet_sha256": _snippet_sha256(subject[idx : idx + len(needle)]),
        }
    idx = body.find(needle)
    if idx != -1:
        return {
            "source": "BODY_C14N",
            "start": idx,
            "end": idx + len(needle),
            "snippet_redacted": body[idx : idx + len(needle)],
            "snippet_sha256": _snippet_sha256(body[idx : idx + len(needle)]),
        }
    return None


def merge_llm_extraction_into_result(
    *,
    config: IEIMConfig,
    extraction_result: dict[str, Any],
    llm_output: dict[str, Any],
    subject_redacted: str,
    body_redacted: str,
) -> dict[str, Any]:
    sets = load_canonical_label_sets()

    entities_out = list(extraction_result.get("entities") or [])
    existing_keys: set[tuple[str, str]] = set()
    for e in entities_out:
        if not isinstance(e, dict):
            continue
        existing_keys.add((str(e.get("entity_type") or ""), str(e.get("value_sha256") or "")))

    entities_raw = _require_list(llm_output.get("entities"), path="llm.entities")
    for idx, it in enumerate(entities_raw):
        if not isinstance(it, dict):
            raise LLMMappingError(f"llm.entities[{idx}] must be an object")
        entity_type = _require_non_empty_str(it.get("entity_type"), path=f"llm.entities[{idx}].entity_type")
        if entity_type not in sets["ENT"]:
            raise LLMMappingError(f"llm.entities[{idx}].entity_type not canonical: {entity_type}")

        snippets = _require_list(it.get("evidence_snippets"), path=f"llm.entities[{idx}].evidence_snippets")
        if not snippets:
            continue

        value: Optional[str] = None
        for s in snippets:
            s = _require_non_empty_str(s, path=f"llm.entities[{idx}].evidence_snippets[*]")
            value = _first_value_match(entity_type=entity_type, text=s)
            if value:
                break
        if not value:
            continue

        provenance = _provenance_for_value(value=value, subject=subject_redacted, body=body_redacted)
        if provenance is None:
            continue

        store_mode = "FULL"
        stored_value: Optional[str] = value
        value_redacted: Optional[str] = value
        if entity_type == "ENT_IBAN":
            store_mode = config.extraction.iban_policy.store_mode
            value_redacted = _iban_redact(value)
            if store_mode == "HASH_ONLY":
                stored_value = None

        value_sha = sha256_prefixed(value.encode("utf-8"))
        key = (entity_type, value_sha)
        if key in existing_keys:
            continue
        existing_keys.add(key)

        entities_out.append(
            {
                "entity_type": entity_type,
                "value": stored_value,
                "value_redacted": value_redacted,
                "value_sha256": value_sha,
                "store_mode": store_mode,
                "confidence": float(it.get("confidence") or 0.0),
                "provenance": provenance,
            }
        )

    merged = dict(extraction_result)
    merged["entities"] = entities_out
    return merged
