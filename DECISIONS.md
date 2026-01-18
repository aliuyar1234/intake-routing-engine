# DECISIONS — Architecture and Governance Records

This file contains decision records required for the IEIM implementation.

## DR-001 — Tamper-evident audit hash chain

- **Problem**: A mutable audit table can be altered after the fact without detection.
- **Decision**: Store audit events as append-only records with `prev_event_hash` and `event_hash` per `(message_id, run_id)` chain and provide a verifier job.
- **Why**: Improves audit integrity and enables deterministic detection of tampering.
- **Tradeoffs**: Slight storage overhead and periodic verification cost.
- **Affected FR/NFR**: FR-015, NFR-006, NFR-009.
- **Affected files**:
  - `spec/07_AUDIT_GOVERNANCE.md`
  - `schemas/audit_event.schema.json`
  - `scripts/validate_schemas.py`
  - `runbooks/ops_monitoring.md`

## DR-002 — Disagreement gate (rules vs model vs LLM) triggers review

- **Problem**: A single classifier can mislabel high-impact intents (legal, GDPR, fraud), causing dangerous routing.
- **Decision**: Implement a deterministic disagreement gate: if high-impact rule signals conflict with model/LLM outputs or confidence is below thresholds, set status to review.
- **Why**: Reduces misrouting and enforces fail-closed behavior.
- **Tradeoffs**: Increases HITL volume in borderline cases.
- **Affected FR/NFR**: FR-007, FR-010, NFR-012.
- **Affected files**:
  - `spec/05_CLASSIFICATION_AND_LLM.md`
  - `spec/06_ROUTING_RULES.md`
  - `prompts/prompt_contract.md`

## DR-003 — Audit minimization: hashes + redacted evidence only

- **Problem**: Audit logs can become a PII exfiltration vector.
- **Decision**: Audit events store only hashes, offsets, and redacted snippets with strict length limits; full text remains in secure stores.
- **Why**: Improves privacy and reduces compliance risk.
- **Tradeoffs**: Debugging requires privileged access to secure preview.
- **Affected FR/NFR**: FR-015, NFR-005, NFR-004.
- **Affected files**:
  - `spec/07_AUDIT_GOVERNANCE.md`
  - `spec/08_SECURITY_PRIVACY.md`
  - `schemas/audit_event.schema.json`
  - `scripts/check_label_consistency.py`

## DR-004 — Default technology stack

- **Problem**: The implementation requires strong NLP/OCR integration and fast iteration while meeting enterprise NFRs.
- **Decision**: Use a Python-first stack (FastAPI + Pydantic + PostgreSQL + Kafka/Redpanda + S3-compatible object storage + OpenTelemetry).
- **Why**: Balances time-to-ship, hiring availability, determinism, and on-prem/hybrid deployment.
- **Tradeoffs**: Performance-critical hotspots may require Go/Rust later.
- **Affected FR/NFR**: NFR-002, NFR-011.
- **Affected files**:
  - `tech/STACK.md`
  - `tech/ARCH_DECISIONS.md`

## DR-005 - decision_hash canonical input (identity stage)

- **Problem**: `decision_hash` must be timestamp-free and reproducible, while binding a decision to its config and evidence without leaking full raw content.
- **Decision**: For the identity stage, compute `decision_hash = sha256( JCS(canonical_decision_input) )`, where `canonical_decision_input` contains:
  - `system_id` and `canonical_spec_semver` (from the selected runtime config)
  - `stage`
  - `message_fingerprint` and `raw_mime_sha256`
  - `config_ref` (`config_path` + `config_sha256`) and `determinism_mode`
  - decision summary: `status`, `selected` (entity type/id/score), `top_k` (including signals and evidence snippet hashes), and thresholds
- **Why**: Ensures deterministic replay can validate that the same inputs, config, and produced decision yield the same `decision_hash`, while excluding wall-clock timestamps and run-scoped identifiers.
- **Tradeoffs**: Any config change (even unrelated keys) changes `config_sha256` and therefore `decision_hash` (intended, since the config snapshot is part of the decision contract).
- **Affected FR/NFR**: FR-015, NFR-009.
- **Affected files**:
  - `spec/07_AUDIT_GOVERNANCE.md`
  - `ieim/determinism/jcs.py`
  - `ieim/determinism/decision_hash.py`
  - `ieim/identity/resolver.py`
  - `data/samples/gold/*.identity.json`

## DR-006 - decision_hash canonical input (classification stage)

- **Problem**: `decision_hash` must be timestamp-free and reproducible for classification, while binding outputs to the config and evidence without leaking sensitive content.
- **Decision**: For the classification stage, compute `decision_hash = sha256( JCS(canonical_decision_input) )`, where `canonical_decision_input` contains:
  - `system_id` and `canonical_spec_semver` (from the selected runtime config)
  - `stage`
  - `message_fingerprint` and `raw_mime_sha256`
  - `config_ref` (`config_path` + `config_sha256`) and `determinism_mode`
  - LLM identifiers (`enabled`, provider/model identifiers, prompt versions) as part of the decision contract
  - decision summary: intents and risk flags including evidence `snippet_sha256` only (no full snippet text), plus primary intent, product line, urgency, and rules version
- **Why**: Enables deterministic replay and audit verification that the same inputs and config yield the same classification decision.
- **Tradeoffs**: Any config change changes `config_sha256` and therefore changes `decision_hash` (intended).
- **Affected FR/NFR**: FR-015, NFR-011.
- **Affected files**:
  - `ieim/classify/classifier.py`
  - `ieim/determinism/jcs.py`
  - `ieim/determinism/decision_hash.py`
  - `data/samples/gold/*.classification.json`

## DR-007 - decision_hash canonical input (routing stage)

- **Problem**: Routing decisions must be replayable and verifiable. `decision_hash` must bind the routing decision to the exact ruleset and inputs without including timestamps.
- **Decision**: For the routing stage, compute `decision_hash = sha256( JCS(canonical_decision_input) )`, where `canonical_decision_input` contains:
  - `system_id` and `canonical_spec_semver` (from the selected runtime config)
  - `stage`
  - `message_fingerprint` and `raw_mime_sha256`
  - `config_ref` (`config_path` + `config_sha256`) and `determinism_mode`
  - `rules_ref` (`ruleset_path` + `ruleset_sha256` + `ruleset_version`)
  - routing inputs: `identity_status`, `primary_intent`, `product_line`, `urgency`, `risk_flags`
  - decision summary: `queue_id`, `sla_id`, `priority`, `actions`, `rule_id`, `fail_closed`, `fail_closed_reason`
- **Why**: Ensures deterministic replay can validate routing behavior against the pinned ruleset and inputs.
- **Tradeoffs**: Any ruleset or config change changes `decision_hash` (intended).
- **Affected FR/NFR**: FR-010, FR-015, NFR-011.
- **Affected files**:
  - `ieim/route/evaluator.py`
  - `ieim/determinism/jcs.py`
  - `ieim/determinism/decision_hash.py`
  - `data/samples/gold/*.routing.json`
