# Scope

IEIM (Intake Routing Engine) is an enterprise system that processes inbound emails (including attachments) from **ingestion** to **deterministic routing** into teams/queues/workflows, with **identity resolution**, **classification**, **entity extraction**, **immutable auditing**, and **human-in-the-loop (HITL)** gates for uncertainty.

The design is **fail-closed** by default: if the system cannot safely associate to a customer/policy/claim or cannot safely route, it produces a review or request-for-information outcome rather than silently making a wrong decision.

Canonical IDs, labels, schema `$id` values, CLI literals, and paths are defined once in `spec/00_CANONICAL.md`.

## In scope

- Mail ingestion via M365 Graph, IMAP, or SMTP gateway
- Immutable raw storage of MIME and attachments (append-only, never overwritten)
- Normalization: MIME parsing, canonicalization, language detection, thread metadata
- Attachment processing: antivirus scanning, file-type detection, text extraction, OCR for scanned documents
- Identity resolution with Top-K candidates plus evidence spans and confidence
- Classification: multi-label intent, product line, urgency/SLA, risk flags
- Extraction: key entities (policy number, claim number, customer number, date, location, document types); optional IBAN under strict privacy policy
- Deterministic routing based on versioned decision tables and risk overrides
- Case/ticket system adapter (create/update, attach original email/files, add drafts)
- Optional reply drafts (approval-gated; never automatically sent)
- HITL review UI requirements and correction workflow; feedback stored for offline improvement
- Immutable audit events per pipeline stage with hashes, versions, and evidence references
- Enterprise NFRs: RBAC, encryption, retention, observability, cost guardrails, reproducibility

## Out of scope

- Claim adjudication, settlement decisions, payments
- Pricing, underwriting, policy quote calculations
- Autonomous sending of emails or autonomous customer communication
- Full DMS/ECM product (only an adapter interface is specified)
- Data lake or analytics platform (only minimal events/metrics are specified)

## Hard guarantees

- Single Definition Rule: all canonical IDs and label sets live only in `spec/00_CANONICAL.md`
- Fail-closed: uncertainty results in review or request-for-information draft
- Immutability: raw inputs and audit events are append-only
- Auditability: each decision includes evidence references, hashes, rule/model/prompt versions
- Determinism mode: routing and identity scoring are reproducible with timestamp-free decision hashes

## Functional requirements (FR)

Each requirement includes acceptance criteria and fail-closed conditions.

### FR-001 Ingestion

Requirement: Ingest emails from supported sources and capture raw MIME and attachments.

Acceptance criteria:
- Ingest from at least one source in production (M365 Graph, IMAP, or SMTP gateway).
- Ingestion is idempotent (no duplicate processing) using a durable cursor.
- For each ingested email, raw MIME is stored and referenced by URI and SHA-256.

Fail-closed:
- If raw MIME cannot be fetched or stored, route to ingestion failure review queue and emit an audit event.

### FR-002 Raw storage immutability

Requirement: Raw store is append-only and supports retention and integrity verification.

Acceptance criteria:
- Stored raw artifacts (MIME and attachment bytes) are never overwritten.
- Each artifact has a content hash recorded in normalized metadata.
- Retention deletion is performed by explicit jobs and is audit logged.

Fail-closed:
- If immutability cannot be guaranteed in the configured backend, ingestion must stop with a hard error.

### FR-003 Normalization

Requirement: Parse MIME, extract canonicalized subject/body, and produce a schema-valid NormalizedMessage.

Acceptance criteria:
- Normalization produces instances that validate against `schemas/normalized_message.schema.json`.
- Canonicalization is deterministic and documented.

Fail-closed:
- If normalization fails, create a review item and emit an audit event with error classification.

### FR-004 Attachment processing

Requirement: Process attachments with AV gating and text extraction/OCR.

Acceptance criteria:
- Each attachment produces a schema-valid AttachmentArtifact.
- AV status is recorded and influences routing.
- Extracted text and OCR confidence are recorded when applicable.

Fail-closed:
- If AV status is infected or suspicious, case creation is blocked and routed to security review.

### FR-005 Identity candidate retrieval

Requirement: Retrieve identity candidates from authoritative systems using extracted keys.

Acceptance criteria:
- Candidate retrieval uses policy/claim/customer identifiers and sender context.
- Candidate retrieval is logged with evidence and lookup sources.

Fail-closed:
- If identity lookup backends are unavailable, identity resolution must return review-required status.

### FR-006 Identity ranking and thresholds

Requirement: Rank candidates deterministically and select only when thresholds are met.

Acceptance criteria:
- Output validates against `schemas/identity_resolution_result.schema.json`.
- Selection occurs only when configured score and margin thresholds are met.

Fail-closed:
- Ties or near ties produce review-required status.

### FR-007 Classification

Requirement: Classify email into intent set, primary intent, product line, urgency, and risk flags.

Acceptance criteria:
- Output validates against `schemas/classification_result.schema.json`.
- Multi-label intent supported.
- Risk flags include at least legal, regulatory, fraud, privacy, and security malware.

Fail-closed:
- Low confidence or disagreement for high-impact categories routes to classification review.

### FR-008 Entity extraction

Requirement: Extract structured entities with provenance.

Acceptance criteria:
- Output validates against `schemas/extraction_result.schema.json`.
- Provenance includes source and character offsets for evidence.

Fail-closed:
- For sensitive entities (bank details, ID documents), if policy forbids full capture, extraction must redact and store only hashes.

### FR-009 Request-for-information generation

Requirement: When identity is uncertain, generate a minimal request-for-information draft.

Acceptance criteria:
- Draft uses approved templates.
- Draft asks only for the minimum necessary information.

Fail-closed:
- Drafts are never sent automatically.

### FR-010 Deterministic routing

Requirement: Deterministically map (identity status, classification, risk flags) to queue/SLA/actions.

Acceptance criteria:
- Routing uses a versioned ruleset and produces schema-valid RoutingDecision.
- Risk overrides apply before regular rules.

Fail-closed:
- If no rule matches, route to general intake review.

### FR-011 Case/ticket adapter

Requirement: Create or update a case in a downstream system.

Acceptance criteria:
- Adapter supports idempotent create and attachment upload.
- Routing actions drive adapter calls.

Fail-closed:
- If the adapter fails, route to case-create-failure review and emit an audit event.

### FR-012 Draft reply creation

Requirement: Optionally generate a draft reply.

Acceptance criteria:
- Draft is created only when allowed by policy and configuration.

Fail-closed:
- Drafts require human approval and cannot be sent by IEIM.

### FR-013 HITL review

Requirement: Provide a review workflow for uncertain identity/classification/routing.

Acceptance criteria:
- Reviewers can see evidence, candidate lists, and decisions.
- Review corrections are stored with full audit trail.

Fail-closed:
- Any reviewer action must be audited; no silent overrides.

### FR-014 Feedback capture

Requirement: Capture corrections as structured feedback for offline improvements.

Acceptance criteria:
- Corrections are stored as versioned feedback records.
- Production does not auto-learn; updates require governance.

Fail-closed:
- If feedback storage is unavailable, proceed with normal routing but log the feedback loss as an audit event.

### FR-015 Audit events

Requirement: Emit immutable audit events for every stage.

Acceptance criteria:
- Audit events validate against `schemas/audit_event.schema.json`.
- Audit store is append-only and supports hash-chain verification.

Fail-closed:
- If audit emission fails, processing halts for that message and routes to ingestion failure review.

### FR-016 Reprocessing

Requirement: Support deterministic replay of a message with pinned artifacts and versions.

Acceptance criteria:
- Reprocessing uses the same raw artifacts and recorded versions.
- Outputs are reproducible in determinism mode.

Fail-closed:
- If required artifacts or versions are missing, reprocessing stops with review-required status.

### FR-017 Ruleset change management

Requirement: Routing and ruleset changes require approvals, versioning, and regression tests.

Acceptance criteria:
- Ruleset changes require a version bump and a decision record.
- The sample corpus is revalidated on every change.

Fail-closed:
- Unapproved ruleset changes must not be deployed.

### FR-018 Observability

Requirement: Provide metrics, logs, and traces for operations.

Acceptance criteria:
- Metrics include throughput, latency, HITL rate, cost per email, mis-association and misroute rates.
- Logs and traces correlate via message_id and run_id.

Fail-closed:
- Observability loss triggers degraded-mode alarms and operational response.

## Non-functional requirements (NFR)

### NFR-001 Reliability

- Target availability: 99.9% monthly for ingestion and routing.
- No single point of failure in the critical path for production deployments.

### NFR-002 Performance

- Sustained throughput is configurable and horizontally scalable.
- Routing decision time (post-normalization) is bounded and does not depend on external systems in determinism mode.

### NFR-003 Security

- Encryption in transit (mTLS) and at rest (KMS/HSM-backed) for all stores.
- Strict network egress allowlist.

### NFR-004 Privacy

- Data minimization in audit logs (hashes + redacted snippets only).
- Sensitive entities are redacted or hashed according to policy.

### NFR-005 Compliance and retention

- Retention policies are configurable and enforced by audited jobs.
- Data residency is enforced by deployment controls.

### NFR-006 Audit integrity

- Audit store is append-only.
- Hash-chain verification can detect tampering.

### NFR-007 Operability

- Health checks, runbooks, dashboards, and incident response processes exist.
- Deterministic replay supports incident investigation.

### NFR-008 Cost control

- Token budgets and rate limits enforced for LLM usage.
- Caching and staged gating to minimize LLM calls.

### NFR-009 Maintainability

- Schemas and canonical values are versioned.
- Breaking changes require version bump and compatibility notes.

### NFR-010 Scalability

- Horizontal scaling for workers; partitioning by message_id/run_id.
- Backpressure and queue length alarms.

### NFR-011 Determinism and reproducibility

- Determinism mode produces stable outputs given the same inputs and artifact versions.
- Decision hashes are timestamp-free.

### NFR-012 Safety (fail-closed)

- High-impact ambiguity always routes to review.
- Security and privacy risks override normal routing.
