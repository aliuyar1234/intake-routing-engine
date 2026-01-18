# Architecture

This section describes IEIM’s logical and physical architecture, including data stores and integration points. Canonical IDs, labels, and paths are defined in `spec/00_CANONICAL.md`.

## End-to-end flow

```mermaid
flowchart LR
  A[Mail Ingestion] --> B[Raw Store (immutable)]
  B --> C[Normalize]
  C --> D[Attachment Processing]
  D --> E[Identity Resolution]
  E --> F[Classification (gated)]
  F --> G[Extraction]
  G --> H[Routing Engine (deterministic)]
  H --> I[Case/Ticket Adapter]
  H --> J[HITL Gate]
  J -->|review| K[Review UI]
  K --> H
  C --> L[Audit Store]
  D --> L
  E --> L
  F --> L
  G --> L
  H --> L
  I --> L
  K --> L
```

## Component model

The system is decomposed into services and adapters. The module identifiers used for traceability are listed in `spec/00_CANONICAL.md`.

### Core services

| Service | Responsibilities | Notes |
|---|---|---|
| Ingestion service | Connectors for M365 Graph, IMAP, SMTP gateway; idempotent intake | At-least-once + dedupe |
| Raw store service | Append-only storage of MIME and attachment bytes | Never overwrite |
| Normalization service | MIME parsing, canonicalization, language detection, thread metadata | Produces NormalizedMessage |
| Attachment service | AV scan, file type detect, text extract, OCR | Produces AttachmentArtifact |
| Identity service | Candidate retrieval + deterministic scoring + Top-K + evidence | Fail-closed |
| Classification service | Rules → lightweight model → LLM (gated) | Strict JSON outputs |
| Extraction service | Entities + provenance + validation | High-impact entities gate |
| Routing service | Deterministic decision tables + hard overrides | Versioned rulesets |
| Case adapter service | Create/update cases, attach original email/files, add drafts | Idempotent keys |
| Audit logger | Append-only audit events + hash chain | Tamper-evident |
| Review UI/API | Human review, corrections, approvals | RBAC-gated |

### Stores

| Store | Contents | Immutability |
|---|---|---|
| Object storage (raw) | MIME and attachment bytes | Append-only (no overwrite) |
| Object storage (derived) | Extracted text artifacts and OCR output | Append-only, versioned by hashes |
| Normalized DB | NormalizedMessage and derived results | Mutable via versioned records; never rewrite raw |
| Audit store | AuditEvent append-only events with hash chain | Append-only |
| Cache | LLM result cache keyed by fingerprints and versions | TTL-based |

## Deployment variants

### On-prem
- All services and stores run within a controlled network zone.
- LLM use is either disabled or served by an on-prem model endpoint.

### Hybrid (recommended)
- Core pipeline and storage remain on-prem/private cloud.
- External LLM is optional and only enabled through a redaction/minimization gateway.

### Cloud
- Fully hosted in a single-tenant environment with private networking, customer-managed keys, and strict DLP.

Recommendation rationale: hybrid provides the best balance of compliance, model quality, and operational scalability while preserving a deterministic and review-safe fallback.

## Integration boundaries

- Mail ingestion adapter boundary: `interfaces/mail_ingest_adapter.md`
- Case/ticket system adapter boundary: `interfaces/case_system_adapter.md`
- Optional DMS/ECM adapter boundary: `interfaces/dms_adapter.md`

## Backpressure and failure handling

- The pipeline is event-driven. Each stage emits an audit event and produces a persisted output before acknowledging upstream work.
- When dependencies are unavailable, the system must either retry within policy or fail closed to a review queue.
