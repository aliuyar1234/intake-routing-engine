from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence

import yaml


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _discover_pack_root(start: Path) -> Optional[Path]:
    for p in [start] + list(start.parents):
        if (p / "MANIFEST.sha256").is_file():
            return p
    return None


def _stable_repo_relative_path(path: Path) -> str:
    try:
        resolved = path.resolve()
    except Exception:
        return path.as_posix()

    root = _discover_pack_root(resolved)
    if root is None:
        return path.as_posix()
    try:
        return resolved.relative_to(root).as_posix()
    except Exception:
        return path.as_posix()


def _require_dict(obj: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"{path} must be a mapping")
    return obj


def _require_str(obj: Any, *, path: str) -> str:
    if not isinstance(obj, str) or not obj:
        raise ValueError(f"{path} must be a non-empty string")
    return obj


def _require_bool(obj: Any, *, path: str) -> bool:
    if not isinstance(obj, bool):
        raise ValueError(f"{path} must be a boolean")
    return obj


def _require_int(obj: Any, *, path: str) -> int:
    if not isinstance(obj, int):
        raise ValueError(f"{path} must be an integer")
    return obj


def _require_float(obj: Any, *, path: str) -> float:
    if isinstance(obj, (int, float)):
        return float(obj)
    raise ValueError(f"{path} must be a number")


@dataclass(frozen=True)
class LLMConfig:
    enabled: bool
    provider: str
    model_name: str
    model_version: str
    prompt_versions: dict[str, str]
    token_budgets: dict[str, int]
    max_calls_per_day: int
    thresholds: "LLMThresholds"


@dataclass(frozen=True)
class LLMClassificationThresholds:
    primary_intent_min: float
    product_line_min: float
    urgency_min: float
    risk_flag_min: float


@dataclass(frozen=True)
class LLMExtractionThresholds:
    high_value_entity_min: float
    other_entity_min: float
    high_value_entity_types: Sequence[str]


@dataclass(frozen=True)
class LLMThresholds:
    classification: LLMClassificationThresholds
    extraction: LLMExtractionThresholds


@dataclass(frozen=True)
class PipelineConfig:
    mode: str


@dataclass(frozen=True)
class ClassificationConfig:
    min_confidence_for_auto: float
    rules_version: str
    llm: LLMConfig


@dataclass(frozen=True)
class IBANPolicy:
    enabled: bool
    store_mode: str


@dataclass(frozen=True)
class ExtractionConfig:
    iban_policy: IBANPolicy


@dataclass(frozen=True)
class RoutingConfig:
    ruleset_path: str
    ruleset_version: str


@dataclass(frozen=True)
class IncidentConfig:
    force_review: bool
    force_review_queue_id: str
    disable_llm: bool
    block_case_create_risk_flags_any: Sequence[str]


@dataclass(frozen=True)
class IEIMConfig:
    system_id: str
    canonical_spec_semver: str
    config_path: str
    config_sha256: str
    determinism_mode: bool
    supported_languages: Sequence[str]
    pipeline: PipelineConfig
    incident: IncidentConfig
    classification: ClassificationConfig
    extraction: ExtractionConfig
    routing: RoutingConfig


def load_config(*, path: Path) -> IEIMConfig:
    data_bytes = path.read_bytes()
    cfg = yaml.safe_load(data_bytes.decode("utf-8"))
    cfg = _require_dict(cfg, path="config")

    pack = _require_dict(cfg.get("pack"), path="pack")
    system_id = _require_str(pack.get("system_id"), path="pack.system_id")
    canonical_spec_semver = _require_str(
        pack.get("canonical_spec_semver"), path="pack.canonical_spec_semver"
    )

    runtime = _require_dict(cfg.get("runtime"), path="runtime")
    determinism_mode = _require_bool(runtime.get("determinism_mode"), path="runtime.determinism_mode")
    supported_languages_raw = runtime.get("supported_languages")
    if not isinstance(supported_languages_raw, list) or not all(
        isinstance(x, str) and x for x in supported_languages_raw
    ):
        raise ValueError("runtime.supported_languages must be a list of non-empty strings")
    supported_languages = tuple(supported_languages_raw)

    pipeline = _require_dict(cfg.get("pipeline"), path="pipeline")
    pipeline_mode = _require_str(pipeline.get("mode"), path="pipeline.mode")
    if pipeline_mode not in {"BASELINE", "LLM_FIRST"}:
        raise ValueError("pipeline.mode must be BASELINE or LLM_FIRST")

    classification = _require_dict(cfg.get("classification"), path="classification")
    min_confidence_for_auto = _require_float(
        classification.get("min_confidence_for_auto"), path="classification.min_confidence_for_auto"
    )
    rules_version = _require_str(classification.get("rules_version"), path="classification.rules_version")

    llm = _require_dict(classification.get("llm"), path="classification.llm")
    prompt_versions_obj = _require_dict(llm.get("prompt_versions"), path="classification.llm.prompt_versions")
    prompt_versions: dict[str, str] = {}
    for k, v in prompt_versions_obj.items():
        prompt_versions[_require_str(k, path="classification.llm.prompt_versions.<key>")] = _require_str(
            v, path=f"classification.llm.prompt_versions.{k}"
        )

    token_budgets_obj = _require_dict(llm.get("token_budgets"), path="classification.llm.token_budgets")
    token_budgets: dict[str, int] = {}
    for k, v in token_budgets_obj.items():
        token_budgets[_require_str(k, path="classification.llm.token_budgets.<key>")] = _require_int(
            v, path=f"classification.llm.token_budgets.{k}"
        )

    thresholds_obj = _require_dict(llm.get("thresholds"), path="classification.llm.thresholds")
    cls_thresholds_obj = _require_dict(
        thresholds_obj.get("classification"), path="classification.llm.thresholds.classification"
    )
    ex_thresholds_obj = _require_dict(
        thresholds_obj.get("extraction"), path="classification.llm.thresholds.extraction"
    )
    high_value_entity_types_raw = ex_thresholds_obj.get("high_value_entity_types")
    if not isinstance(high_value_entity_types_raw, list) or not all(
        isinstance(x, str) and x for x in high_value_entity_types_raw
    ):
        raise ValueError(
            "classification.llm.thresholds.extraction.high_value_entity_types must be a list of non-empty strings"
        )

    thresholds = LLMThresholds(
        classification=LLMClassificationThresholds(
            primary_intent_min=_require_float(
                cls_thresholds_obj.get("primary_intent_min"),
                path="classification.llm.thresholds.classification.primary_intent_min",
            ),
            product_line_min=_require_float(
                cls_thresholds_obj.get("product_line_min"),
                path="classification.llm.thresholds.classification.product_line_min",
            ),
            urgency_min=_require_float(
                cls_thresholds_obj.get("urgency_min"),
                path="classification.llm.thresholds.classification.urgency_min",
            ),
            risk_flag_min=_require_float(
                cls_thresholds_obj.get("risk_flag_min"),
                path="classification.llm.thresholds.classification.risk_flag_min",
            ),
        ),
        extraction=LLMExtractionThresholds(
            high_value_entity_min=_require_float(
                ex_thresholds_obj.get("high_value_entity_min"),
                path="classification.llm.thresholds.extraction.high_value_entity_min",
            ),
            other_entity_min=_require_float(
                ex_thresholds_obj.get("other_entity_min"),
                path="classification.llm.thresholds.extraction.other_entity_min",
            ),
            high_value_entity_types=tuple(high_value_entity_types_raw),
        ),
    )

    llm_cfg = LLMConfig(
        enabled=_require_bool(llm.get("enabled"), path="classification.llm.enabled"),
        provider=_require_str(llm.get("provider"), path="classification.llm.provider"),
        model_name=_require_str(llm.get("model_name"), path="classification.llm.model_name"),
        model_version=_require_str(llm.get("model_version"), path="classification.llm.model_version"),
        prompt_versions=prompt_versions,
        token_budgets=token_budgets,
        max_calls_per_day=_require_int(llm.get("max_calls_per_day"), path="classification.llm.max_calls_per_day"),
        thresholds=thresholds,
    )

    extraction = _require_dict(cfg.get("extraction"), path="extraction")
    iban_policy_obj = _require_dict(extraction.get("iban_policy"), path="extraction.iban_policy")
    iban_policy = IBANPolicy(
        enabled=_require_bool(iban_policy_obj.get("enabled"), path="extraction.iban_policy.enabled"),
        store_mode=_require_str(iban_policy_obj.get("store_mode"), path="extraction.iban_policy.store_mode"),
    )

    routing = _require_dict(cfg.get("routing"), path="routing")
    routing_cfg = RoutingConfig(
        ruleset_path=_require_str(routing.get("ruleset_path"), path="routing.ruleset_path"),
        ruleset_version=_require_str(routing.get("ruleset_version"), path="routing.ruleset_version"),
    )

    incident_obj = cfg.get("incident") or {}
    if not isinstance(incident_obj, dict):
        raise ValueError("incident must be a mapping")
    force_review = incident_obj.get("force_review", False)
    if not isinstance(force_review, bool):
        raise ValueError("incident.force_review must be a boolean")
    disable_llm = incident_obj.get("disable_llm", False)
    if not isinstance(disable_llm, bool):
        raise ValueError("incident.disable_llm must be a boolean")

    force_review_queue_id = incident_obj.get("force_review_queue_id", "QUEUE_INTAKE_REVIEW_GENERAL")
    if not isinstance(force_review_queue_id, str) or not force_review_queue_id:
        raise ValueError("incident.force_review_queue_id must be a non-empty string")

    block_case_create_risk_flags_any = incident_obj.get("block_case_create_risk_flags_any", [])
    if not isinstance(block_case_create_risk_flags_any, list) or not all(
        isinstance(x, str) and x for x in block_case_create_risk_flags_any
    ):
        raise ValueError("incident.block_case_create_risk_flags_any must be a list of non-empty strings")

    return IEIMConfig(
        system_id=system_id,
        canonical_spec_semver=canonical_spec_semver,
        config_path=_stable_repo_relative_path(path),
        config_sha256=_sha256_prefixed(data_bytes),
        determinism_mode=determinism_mode,
        supported_languages=supported_languages,
        pipeline=PipelineConfig(mode=pipeline_mode),
        incident=IncidentConfig(
            force_review=force_review,
            force_review_queue_id=force_review_queue_id,
            disable_llm=disable_llm,
            block_case_create_risk_flags_any=tuple(block_case_create_risk_flags_any),
        ),
        classification=ClassificationConfig(
            min_confidence_for_auto=min_confidence_for_auto,
            rules_version=rules_version,
            llm=llm_cfg,
        ),
        extraction=ExtractionConfig(iban_policy=iban_policy),
        routing=routing_cfg,
    )
