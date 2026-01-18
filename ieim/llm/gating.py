from __future__ import annotations

from dataclasses import dataclass

from ieim.config import IEIMConfig


@dataclass(frozen=True)
class LLMGateDecision:
    allowed: bool
    reason: str


def should_call_llm_classify(*, config: IEIMConfig, deterministic_classification: dict) -> LLMGateDecision:
    if config.determinism_mode:
        return LLMGateDecision(allowed=False, reason="DETERMINISM_MODE")
    if config.incident.disable_llm:
        return LLMGateDecision(allowed=False, reason="INCIDENT_DISABLE_LLM")
    if not config.classification.llm.enabled:
        return LLMGateDecision(allowed=False, reason="DISABLED")
    if config.classification.llm.provider == "disabled":
        return LLMGateDecision(allowed=False, reason="DISABLED_PROVIDER")

    risk_flags = deterministic_classification.get("risk_flags") or []
    if risk_flags:
        return LLMGateDecision(allowed=False, reason="RISK_FLAGS_PRESENT")

    primary = deterministic_classification.get("primary_intent") or {}
    conf = float(primary.get("confidence") or 0.0)
    if conf >= float(config.classification.min_confidence_for_auto):
        return LLMGateDecision(allowed=False, reason="CONFIDENCE_HIGH_ENOUGH")

    return LLMGateDecision(allowed=True, reason="LOW_CONFIDENCE_NO_RISK_FLAGS")


def should_call_llm_extract(*, classify_llm_used: bool, deterministic_extraction: dict) -> LLMGateDecision:
    if not classify_llm_used:
        return LLMGateDecision(allowed=False, reason="CLASSIFY_LLM_NOT_USED")
    entities = deterministic_extraction.get("entities") or []
    if entities:
        return LLMGateDecision(allowed=False, reason="ENTITIES_ALREADY_EXTRACTED")
    return LLMGateDecision(allowed=True, reason="NO_ENTITIES_AND_CLASSIFY_USED_LLM")
