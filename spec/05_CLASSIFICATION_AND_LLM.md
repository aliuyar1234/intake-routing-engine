# Classification and LLM gating

Classification produces:
- multi-label intent set
- product line
- urgency
- risk flags

Canonical label IDs are defined in `spec/00_CANONICAL.md`.

## Pipeline order

1. Deterministic rules (high precision)
2. Lightweight deterministic model (calibrated probabilities)
3. LLM (optional, gated)

## Deterministic rules

Rules should be high precision and produce evidence. Examples of rule families:
- GDPR request language
- legal threat language
- regulatory escalation language
- bounce/auto-reply markers

Rules are versioned and changes require approval; routing safety overrides must be enforced.

## LLM usage policy

LLM calls are optional and must be disabled by default in determinism mode. When enabled:
- Only minimized, redacted inputs may be sent externally
- The model must return strict JSON only
- Outputs are schema validated and label validated
- Failures lead to review (never silent fallback)

## Strict JSON contract

All LLM prompts must comply with `prompts/prompt_contract.md`:
- output is JSON only
- schema must validate
- labels must be canonical
- retry policy is deterministic

## Disagreement gate

If deterministic rules indicate a high-impact outcome and the model/LLM disagrees, the system must:
- prefer the high-precision rule
- route to the safest queue or review if routing-relevant ambiguity remains
- record the disagreement in the audit log

## Cost controls

- Token budgets per stage
- Daily caps for LLM calls
- Cache keyed by message fingerprint and prompt/model versions

Cost controls are configuration-driven and must be recorded in audit events.

## Privacy controls

- Redaction policy must remove or mask sensitive PII in audit logs and in any external LLM request
- IBAN extraction is optional and must be policy-gated
- No full raw attachments are sent to external LLM
