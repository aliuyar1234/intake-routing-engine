# QUALITY_GATES — Definition of Done, Phase Gates, Release Checklist

This document is binding. A phase is complete only when its gate is satisfied.

The phase plan and task list are defined in `spec/09_PHASE_PLAN.md`.

## Global Definition of Done

A phase is done only when all conditions hold:

- All tasks of the phase are implemented.
- All phase-specific unit/integration/E2E tests pass.
- Pack verification passes: `bash scripts/verify_pack.sh`.
- Fail-closed behavior is demonstrably enforced for:
  - identity ambiguity (no silent association)
  - routing ambiguity (no silent misroute)
  - security/privacy overrides (malware/GDPR/legal)
- Determinism mode is reproducible for decision-making stages (identity and routing): same inputs and same versions produce the same `decision_hash`.
- Each stage touched by the phase emits schema-valid `AuditEvent` records.

## Phase gates

### G-001 (P0) — Foundations and SSOT enforcement

Required evidence:
- All JSON Schemas in `schemas/` validate against Draft 2020-12.
- `bash scripts/verify_pack.sh` passes.
- Single Definition Rule holds (only `spec/00_CANONICAL.md` defines canonical tokens).

### G-002 (P1) — Ingestion, raw store, normalization

Required evidence:
- Ingest adapter(s) produce raw MIME artifacts and a schema-valid `NormalizedMessage`.
- Raw store writes are append-only and content-addressed (SHA-256 recorded).
- Idempotency is enforced (duplicate ingestion does not create duplicate processing outputs).

Minimum tests:
- Ingestion adapter integration tests (against stubs).
- Schema validation for produced `NormalizedMessage` instances.

### G-003 (P2) — Attachment processing

Required evidence:
- Each attachment yields a schema-valid `AttachmentArtifact` with SHA-256 and AV status.
- AV status gates behavior:
  - `INFECTED` or `SUSPICIOUS` causes fail-closed security review routing and blocks case creation.
- Text extraction and OCR outputs are stored and referenceable.

Minimum tests:
- AV enforcement tests (infected blocks).
- Extraction/OCR pipeline tests (confidence recorded).

### G-004 (P3) — Identity resolution

Required evidence:
- `IdentityResolutionResult` is deterministic (same candidate set and config yields same ranking).
- Threshold and margin logic is enforced; ties or near-ties produce `IDENTITY_NEEDS_REVIEW`.
- Request-for-information draft generation is produced when identity is unresolved (never auto-sent).

Minimum tests:
- Identity scoring unit tests including tie/near-tie negative cases.
- E2E identity regression against `data/samples/gold/*.identity.json`.

### G-005 (P4) — Classification and extraction

Required evidence:
- `ClassificationResult` and `ExtractionResult` validate against schemas.
- Disagreement gate exists for high-impact categories and fails closed to review.
- Sensitive extraction policy is enforced (e.g., IBAN redacted/hashed if policy forbids full value).

Minimum tests:
- Label-set enforcement tests (no free strings).
- E2E regression against `data/samples/gold/*.classification.json` and `*.extraction.json`.

### G-006 (P5) — Routing engine and case adapter

Required evidence:
- Routing uses the versioned ruleset in `configs/routing_tables/` and is deterministic.
- No-rule-match fails closed to `QUEUE_INTAKE_REVIEW_GENERAL`.
- Case adapter operations are idempotent and honor routing actions:
  - create/update case
  - attach original email and files
  - add request-info and reply drafts as approved artifacts (never sent by IEIM)

Minimum tests:
- Routing unit tests including no-rule-match and override precedence.
- E2E regression against `data/samples/gold/*.routing.json`.
- Case adapter idempotency tests (stub).

### G-007 (P6) — Audit integrity and observability

Required evidence:
- Every pipeline stage emits schema-valid `AuditEvent` records.
- Audit hash chain verification detects tampering.
- `decision_hash` is timestamp-free and reproducible.
- Deterministic reprocess/replay is supported using pinned artifacts and recorded versions.
- Metrics, logs, and traces are emitted and correlate via `message_id` and `run_id`.

Minimum tests:
- Audit chain verification tests.
- Determinism tests for `decision_hash` (replay yields identical hash).

### G-008 (P7) — HITL and governance

Required evidence:
- Review workflow supports identity/classification/routing review with evidence display.
- Corrections are stored as versioned feedback records and are fully audit-linked.
- Governance: no automatic learning in production; promotions require approvals.

Minimum tests:
- HITL workflow integration tests (stub UI/API).
- Feedback record validation tests.

### G-009 (P8) — Production hardening and rollout

Required evidence:
- Deployment automation and runbooks are complete and rehearsed.
- Incident toggles exist (force review, disable LLM, block case creation for subsets).
- Load testing demonstrates target throughput with backpressure and alarms.

Minimum tests:
- Load test report produced and stored.
- Operational readiness review completed.

## Release checklist (pre-production)

Before any production rollout:

1. `bash scripts/verify_pack.sh` passes.
2. Golden corpus E2E tests pass (`tests/e2e_spec.md`).
3. Audit chain verification job exists and detects tampering.
4. RBAC role mapping reviewed (least privilege).
5. Retention jobs configured and tested.
6. Cost guardrails configured and enforced.
7. Incident runbooks reviewed and on-call readiness confirmed.

---

## Enterprise productization gates (P9+)

These gates extend the SSOT pack + reference implementation into an installable, operable enterprise system.

Detailed plan and required decisions: `spec/13_ENTERPRISE_PHASE_PLAN_P9_PLUS.md`

### G-010 (P9) — Production runtime packaging foundation

Required evidence:
- Services start in local mode (API, worker, scheduler).
- Config validation works for `configs/dev.yaml` and `configs/prod.yaml`.
- Store and broker contract tests pass.

Minimum commands:
- `bash scripts/verify_pack.sh`
- `python -B -m unittest discover -s tests -p "test_*.py"`
- `python ieimctl.py config validate --config configs/dev.yaml`
- `python ieimctl.py config validate --config configs/prod.yaml`

### G-011 (P10) — Docker Compose install and demo flow

Required evidence:
- Starter profile runs end-to-end on the sample corpus.
- Production profile starts with secure defaults (least exposed ports, non-root containers).

Minimum commands:
- `bash scripts/verify_pack.sh`
- `python -B -m unittest discover -s tests -p "test_*.py"`
- `docker compose -f deploy/compose/starter/docker-compose.yml up -d --build`
- `python ieimctl.py demo run --config configs/dev.yaml --samples data/samples`
- `docker compose -f deploy/compose/starter/docker-compose.yml down -v`

### G-012 (P11) — Helm install smoke test

Required evidence:
- Chart renders valid manifests and enforces hardening defaults (non-root, no privileged pods).

Minimum commands:
- `bash scripts/verify_pack.sh`
- `python -B -m unittest discover -s tests -p "test_*.py"`
- `helm template ieim deploy/helm/ieim -f deploy/helm/ieim/values.yaml`
- If Helm is not installed: `docker run --rm -v "$PWD:/work" -w /work alpine/helm:3.14.0 template ieim deploy/helm/ieim -f deploy/helm/ieim/values.yaml`

### G-013 (P12) — Auth and HITL readiness

Required evidence:
- Review API endpoints enforce RBAC fail-closed.
- HITL actions create immutable correction records and audit events.

Minimum tests:
- Auth and RBAC tests (JWT validation and authorization matrix).
- Review API contract tests for required endpoints.

Minimum commands:
- `bash scripts/verify_pack.sh`
- `python -B -m unittest discover -s tests -p "test_*.py"`

### G-014 (P13) — Integration readiness

Required evidence:
- At least one mail ingest adapter works end-to-end into the pipeline.
- At least one case adapter creates a case using a mock API and attaches artifacts.
- Failures are audited and routed to failure review queues (no silent drops).

Minimum commands:
- `bash scripts/verify_pack.sh`
- `python -B -m unittest discover -s tests -p "test_*.py"`
- `python ieimctl.py ingest simulate --adapter <adapter> --samples data/samples`
- `python ieimctl.py case simulate --adapter <adapter> --samples data/samples`

### G-015 (P14) — Operability gate

Required evidence:
- Metrics and dashboards are defined and render correctly.
- Alert rules are valid.
- Backup and restore runs successfully in a test environment.
- Retention enforcement works without violating audit immutability.

Minimum commands:
- `bash scripts/verify_pack.sh`
- `python -B -m unittest discover -s tests -p "test_*.py"`
- `python ieimctl.py ops smoke --config configs/dev.yaml`

### G-016 (P15) — Release readiness

Required evidence:
- Release pipeline builds versioned artifacts (images and install artifacts as applicable).
- SBOM and provenance/signing are produced as release artifacts.
- Upgrade checks fail closed if migrations or prerequisites are missing.

Minimum commands:
- `bash scripts/verify_pack.sh`
- `python -B -m unittest discover -s tests -p "test_*.py"`
- `python ieimctl.py upgrade check --config configs/prod.yaml`

### G-017 (P16) — Performance gate

Required evidence:
- Meets agreed throughput/latency targets for the chosen deployment profile.
- Mis-association and misroute risks remain fail-closed (review gates trigger instead of silent errors).

Minimum commands:
- `bash scripts/verify_pack.sh`
- `python ieimctl.py loadtest run --profile enterprise_smoke --config configs/dev.yaml`
