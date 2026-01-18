# Incident response

## Severity

- Sev1: security or privacy incident, malware handling, data exfiltration suspicion, widespread outage
- Sev2: sustained routing/identity failures causing backlog
- Sev3: partial degradation, elevated HITL rate, cost anomalies

## Immediate actions (Sev1)

1. Disable outbound integrations (case adapter) if data leakage is suspected.
2. Enable strict fail-closed mode for identity and routing.
3. Preserve evidence: snapshots of audit store, raw store integrity proofs.
4. Rotate potentially compromised credentials.

## Incident toggles (configuration)

This pack supports incident toggles in the runtime config under `incident` (for example in `configs/prod.yaml`).

Example:

```yaml
incident:
  force_review: true
  force_review_queue_id: "QUEUE_INTAKE_REVIEW_GENERAL"
  disable_llm: true
  block_case_create_risk_flags_any:
    - RISK_LEGAL_THREAT
    - RISK_REGULATORY
```

Behavior:

- `force_review: true` forces routing into the configured review queue and prevents automatic case creation.
- `disable_llm: true` blocks all LLM usage regardless of `classification.llm.enabled`.
- `block_case_create_risk_flags_any` removes `CREATE_CASE` actions and adds `BLOCK_CASE_CREATE` when any listed risk flag is present.

## Investigation checklist

- Identify impacted message_ids and run_ids
- Verify audit hash chain integrity
- Review access logs for privileged operations
- Assess whether sensitive fields were logged contrary to policy

## Recovery

- Restore services from known-good configuration
- Reprocess affected messages using deterministic replay
- Document findings and preventative actions
