# Operations runbook (overview)

This file provides the operational overview. Detailed runbooks are in `runbooks/`.

## Operational principles

- Fail-closed toggles are available to force manual review.
- All raw data and audit events are immutable.
- Keys are rotated and access is regularly reviewed.

## Primary dashboards

- Throughput per stage
- Percent routed to HITL
- Mis-association rate (identity incorrect association)
- Misroute rate (queue wrong)
- SLA compliance per queue
- Cost per email and total model spend
- OCR error rate

## Routine jobs

- Audit hash chain verification (`ieimctl audit verify`)
- Retention lifecycle enforcement (see `runbooks/retention_jobs.md`)
- Cache eviction and cost guardrail enforcement

## Deterministic reprocess/replay

Deterministic replay exists to support incident investigation, audit, and safe reprocessing of failed runs.

Inputs for replay are **only**:
- immutable raw artifacts (raw MIME and attachment bytes) verified by SHA-256
- recorded versions (ruleset version + ruleset hash, schema versions, model/prompt versions)
- the deterministic configuration snapshot for the run

Operational steps:
1. Identify the target `message_id` and the historical run to reproduce using audit events.
2. Fetch raw MIME and attachments using the stored URIs and verify their SHA-256 hashes.
3. Load the recorded ruleset and configuration versions; enable determinism mode for replay.
4. Execute the pipeline stages and emit `AuditEvent` records with `stage=REPROCESS`.
5. Persist outputs as new versioned records; do not overwrite prior derived outputs.
6. Compare the replay `decision_hash` values to the historical `decision_hash` values when versions are identical; any mismatch is an incident signal.

Fail-closed rules for replay:
- If any required artifact is missing, unreadable, or hash-mismatched, replay stops and produces a review-required outcome.
- Replay must not silently create duplicate downstream cases; downstream side effects require explicit, approved operational action.

## Incident modes

- Disable external LLM
- Force all messages to review
- Block case creation for a subset of risk flags

In this pack, these are represented as config toggles under `incident` (see `configs/dev.yaml` and `configs/prod.yaml`).

Example:

```yaml
incident:
  force_review: true
  force_review_queue_id: "QUEUE_INTAKE_REVIEW_GENERAL"
  disable_llm: true
  block_case_create_risk_flags_any: [RISK_LEGAL_THREAT]
```

See:
- Deployment: `runbooks/deployment.md`
- Monitoring: `runbooks/ops_monitoring.md`
- Incidents: `runbooks/incident_response.md`
- Key rotation: `runbooks/key_rotation.md`
- Retention: `runbooks/retention_jobs.md`
- Cost controls: `runbooks/cost_controls.md`
