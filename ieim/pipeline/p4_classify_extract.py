from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ieim.audit.file_audit_log import ArtifactRef, FileAuditLogger, build_audit_event
from ieim.classify.classifier import DeterministicClassifier
from ieim.config import IEIMConfig, load_config
from ieim.extract.extractor import DeterministicExtractor
from ieim.identity.config_select import select_config_path_for_message
from ieim.llm.adapter import LLMAdapter
from ieim.llm.gating import should_call_llm_classify, should_call_llm_extract
from ieim.llm.mapping import (
    LLMMappingError,
    build_classification_result_from_llm,
    merge_llm_extraction_into_result,
)
from ieim.llm.redaction import redact_preserve_length
from ieim.observability.file_observability_log import FileObservabilityLogger, build_observability_event
from ieim.raw_store import sha256_prefixed


def _parse_rfc3339(dt: str) -> datetime:
    if dt.endswith("Z"):
        dt = dt[:-1] + "+00:00"
    return datetime.fromisoformat(dt)


def _load_attachments(*, attachments_dir: Path, nm: dict) -> list[dict]:
    out: list[dict] = []
    for att_id in nm.get("attachment_ids") or []:
        artifact_path = attachments_dir / f"{att_id}.artifact.json"
        if not artifact_path.exists():
            continue
        out.append(json.loads(artifact_path.read_text(encoding="utf-8")))
    return out


def _collect_evidence(*, classification: dict) -> list[dict]:
    out: list[dict] = []

    def add_from_items(items: list[dict]) -> None:
        for it in items:
            for ev in it.get("evidence") or []:
                out.append(ev)

    add_from_items(classification.get("intents") or [])
    add_from_items(classification.get("risk_flags") or [])
    add_from_items([classification.get("product_line") or {}])
    add_from_items([classification.get("urgency") or {}])
    add_from_items([classification.get("primary_intent") or {}])
    return out


def _fail_closed_review_classification(*, cfg: IEIMConfig, nm: dict, deterministic_risk_flags: list[dict]) -> dict:
    from ieim.classify.classifier import _classification_schema_id_and_version
    from ieim.determinism.decision_hash import decision_hash

    schema_id, schema_version = _classification_schema_id_and_version()
    message_id = str(nm["message_id"])
    run_id = str(nm["run_id"])
    created_at = str(nm["ingested_at"])

    subject = redact_preserve_length(str(nm.get("subject_c14n") or ""))
    body = redact_preserve_length(str(nm.get("body_text_c14n") or ""))
    text = body if body else subject
    end = min(20, len(text))
    span = {
        "source": "BODY_C14N" if body else "SUBJECT_C14N",
        "start": 0,
        "end": end,
        "snippet_redacted": text[:end],
        "snippet_sha256": sha256_prefixed(text[:end].encode("utf-8")),
    }

    intents = [{"label": "INTENT_GENERAL_INQUIRY", "confidence": 0.0, "evidence": [span]}]
    primary = intents[0]
    product_line = {"label": "PROD_UNKNOWN", "confidence": 0.0, "evidence": [span]}
    urgency = {"label": "URG_NORMAL", "confidence": 0.0, "evidence": [span]}

    decision_input = {
        "system_id": cfg.system_id,
        "canonical_spec_semver": cfg.canonical_spec_semver,
        "stage": "CLASSIFY",
        "message_fingerprint": str(nm.get("message_fingerprint") or ""),
        "raw_mime_sha256": str(nm.get("raw_mime_sha256") or ""),
        "config_ref": {"config_path": cfg.config_path, "config_sha256": cfg.config_sha256},
        "determinism_mode": cfg.determinism_mode,
        "llm": {
            "enabled": cfg.classification.llm.enabled,
            "provider": cfg.classification.llm.provider,
            "model_name": cfg.classification.llm.model_name,
            "model_version": cfg.classification.llm.model_version,
            "prompt_versions": cfg.classification.llm.prompt_versions,
        },
        "decision": {
            "intents": [
                {
                    "label": "INTENT_GENERAL_INQUIRY",
                    "confidence": 0.0,
                    "evidence": [
                        {
                            "source": span["source"],
                            "start": span["start"],
                            "end": span["end"],
                            "snippet_sha256": span["snippet_sha256"],
                        }
                    ],
                }
            ],
            "primary_intent": {"label": primary["label"], "confidence": primary["confidence"]},
            "product_line": product_line["label"],
            "urgency": urgency["label"],
            "risk_flags": [
                {
                    "label": r.get("label"),
                    "confidence": r.get("confidence"),
                    "evidence": [
                        {
                            "source": e.get("source"),
                            "start": e.get("start"),
                            "end": e.get("end"),
                            "snippet_sha256": e.get("snippet_sha256"),
                        }
                        for e in (r.get("evidence") or [])
                    ],
                }
                for r in (deterministic_risk_flags or [])
                if isinstance(r, dict)
            ],
            "rules_version": cfg.classification.rules_version,
            "min_confidence_for_auto": cfg.classification.min_confidence_for_auto,
        },
    }

    return {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "message_id": message_id,
        "run_id": run_id,
        "intents": intents,
        "primary_intent": primary,
        "product_line": product_line,
        "urgency": urgency,
        "risk_flags": list(deterministic_risk_flags or []),
        "model_info": None,
        "created_at": created_at,
        "decision_hash": decision_hash(decision_input),
    }


@dataclass
class ClassifyExtractRunner:
    repo_root: Path
    normalized_dir: Path
    attachments_dir: Path
    classification_out_dir: Path
    extraction_out_dir: Path
    audit_logger: Optional[FileAuditLogger] = None
    obs_logger: Optional[FileObservabilityLogger] = None
    config_path_override: Optional[Path] = None

    def _load_config(self, *, nm: dict) -> IEIMConfig:
        config_path = self.config_path_override or select_config_path_for_message(
            repo_root=self.repo_root, normalized_message=nm
        )
        return load_config(path=config_path)

    def run(self) -> list[tuple[dict, dict]]:
        produced: list[tuple[dict, dict]] = []
        self.classification_out_dir.mkdir(parents=True, exist_ok=True)
        self.extraction_out_dir.mkdir(parents=True, exist_ok=True)

        for nm_path in sorted(self.normalized_dir.glob("*.json")):
            nm_bytes = nm_path.read_bytes()
            nm = json.loads(nm_bytes.decode("utf-8"))

            cfg = self._load_config(nm=nm)
            attachments = _load_attachments(attachments_dir=self.attachments_dir, nm=nm)

            classifier = DeterministicClassifier(config=cfg)
            t_cls0 = time.perf_counter()
            cls = classifier.classify(normalized_message=nm, attachments=attachments)
            cls_ms = int((time.perf_counter() - t_cls0) * 1000)

            classification_result = cls.result
            classify_model_info = None
            classify_llm_used = False
            subject_redacted = redact_preserve_length(str(nm.get("subject_c14n") or ""))
            body_redacted = redact_preserve_length(str(nm.get("body_text_c14n") or ""))

            gate_cls = should_call_llm_classify(config=cfg, deterministic_classification=classification_result)
            if gate_cls.allowed:
                try:
                    llm = LLMAdapter(repo_root=self.repo_root, config=cfg)
                    llm_resp = llm.classify(
                        normalized_message=nm,
                        message_fingerprint=str(nm.get("message_fingerprint") or ""),
                    )
                    mapped = build_classification_result_from_llm(
                        config=cfg,
                        normalized_message=nm,
                        llm_output=llm_resp.output,
                        llm_model_info=llm_resp.model_info,
                        deterministic_risk_flags=list(cls.result.get("risk_flags") or []),
                    )
                    classification_result = mapped.classification_result
                    subject_redacted = mapped.subject_redacted
                    body_redacted = mapped.body_redacted
                    classify_model_info = llm_resp.model_info
                    classify_llm_used = True
                except (LLMMappingError, Exception):
                    classification_result = _fail_closed_review_classification(
                        cfg=cfg,
                        nm=nm,
                        deterministic_risk_flags=list(cls.result.get("risk_flags") or []),
                    )
                    classify_llm_used = False

            t_ex0 = time.perf_counter()
            extraction = DeterministicExtractor(config=cfg).extract(
                normalized_message=nm, attachments=attachments
            )
            ex_ms = int((time.perf_counter() - t_ex0) * 1000)

            extract_model_info = None
            gate_ex = should_call_llm_extract(
                classify_llm_used=classify_llm_used, deterministic_extraction=extraction
            )
            if gate_ex.allowed:
                try:
                    llm = LLMAdapter(repo_root=self.repo_root, config=cfg)
                    llm_ex = llm.extract(
                        normalized_message=nm,
                        message_fingerprint=str(nm.get("message_fingerprint") or ""),
                        policies={
                            "iban_policy": {
                                "enabled": bool(cfg.extraction.iban_policy.enabled),
                                "store_mode": str(cfg.extraction.iban_policy.store_mode),
                            }
                        },
                    )
                    extraction = merge_llm_extraction_into_result(
                        config=cfg,
                        extraction_result=extraction,
                        llm_output=llm_ex.output,
                        subject_redacted=subject_redacted,
                        body_redacted=body_redacted,
                    )
                    extract_model_info = llm_ex.model_info
                except (LLMMappingError, Exception):
                    extract_model_info = None

            cls_out_path = self.classification_out_dir / f"{classification_result['message_id']}.classification.json"
            cls_out_bytes = (
                json.dumps(classification_result, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
                + b"\n"
            )
            tmp = cls_out_path.with_suffix(cls_out_path.suffix + ".tmp")
            tmp.write_bytes(cls_out_bytes)
            tmp.replace(cls_out_path)

            ex_out_path = self.extraction_out_dir / f"{extraction['message_id']}.extraction.json"
            ex_out_bytes = (
                json.dumps(extraction, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
                + b"\n"
            )
            tmp = ex_out_path.with_suffix(ex_out_path.suffix + ".tmp")
            tmp.write_bytes(ex_out_bytes)
            tmp.replace(ex_out_path)

            if self.obs_logger is not None:
                created_at_dt = _parse_rfc3339(str(nm["ingested_at"]))
                self.obs_logger.append(
                    build_observability_event(
                        event_type="STAGE_COMPLETE",
                        stage="CLASSIFY",
                        message_id=str(nm["message_id"]),
                        run_id=str(nm["run_id"]),
                        occurred_at=created_at_dt,
                        duration_ms=cls_ms,
                        status="OK",
                        fields={
                            "primary_intent": str(
                                classification_result.get("primary_intent", {}).get("label") or ""
                            )
                        },
                    )
                )
                self.obs_logger.append(
                    build_observability_event(
                        event_type="STAGE_COMPLETE",
                        stage="EXTRACT",
                        message_id=str(nm["message_id"]),
                        run_id=str(nm["run_id"]),
                        occurred_at=created_at_dt,
                        duration_ms=ex_ms,
                        status="OK",
                        fields={"entity_count": len(extraction.get("entities") or [])},
                    )
                )

            if self.audit_logger is not None:
                created_at_dt = _parse_rfc3339(str(nm["ingested_at"]))
                nm_ref = ArtifactRef(
                    schema_id=str(nm["schema_id"]),
                    uri=nm_path.name,
                    sha256=sha256_prefixed(nm_bytes),
                )
                cls_ref = ArtifactRef(
                    schema_id=str(classification_result["schema_id"]),
                    uri=cls_out_path.name,
                    sha256=sha256_prefixed(cls_out_bytes),
                )
                ex_ref = ArtifactRef(
                    schema_id=str(extraction["schema_id"]),
                    uri=ex_out_path.name,
                    sha256=sha256_prefixed(ex_out_bytes),
                )

                cls_event = build_audit_event(
                    message_id=str(nm["message_id"]),
                    run_id=str(nm["run_id"]),
                    stage="CLASSIFY",
                    actor_type="SYSTEM",
                    created_at=created_at_dt,
                    input_ref=nm_ref,
                    output_ref=cls_ref,
                    decision_hash=str(classification_result["decision_hash"]),
                    config_ref={
                        "config_path": cfg.config_path,
                        "config_sha256": cfg.config_sha256,
                    },
                    rules_ref=cls.rules_ref,
                    model_info=classify_model_info,
                    evidence=_collect_evidence(classification=classification_result),
                )
                self.audit_logger.append(cls_event)

                ex_event = build_audit_event(
                    message_id=str(nm["message_id"]),
                    run_id=str(nm["run_id"]),
                    stage="EXTRACT",
                    actor_type="SYSTEM",
                    created_at=created_at_dt,
                    input_ref=cls_ref,
                    output_ref=ex_ref,
                    decision_hash=None,
                    config_ref={
                        "config_path": cfg.config_path,
                        "config_sha256": cfg.config_sha256,
                    },
                    rules_ref=None,
                    model_info=extract_model_info,
                    evidence=[],
                )
                self.audit_logger.append(ex_event)

            produced.append((classification_result, extraction))

        return produced
