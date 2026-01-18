# Data model

IEIM uses a small set of versioned, schema-validated objects as the stable contract between pipeline stages. Canonical schema `$id` URNs are defined in `spec/00_CANONICAL.md`. The JSON Schema files live in `schemas/`.

## Core objects

| Object | Purpose | Schema file |
|---|---|---|
| NormalizedMessage | Parsed and canonicalized email representation | `schemas/normalized_message.schema.json` |
| AttachmentArtifact | Stored attachment metadata, AV status, extracted text references | `schemas/attachment_artifact.schema.json` |
| IdentityResolutionResult | Top-K candidate association with evidence + confidence | `schemas/identity_resolution_result.schema.json` |
| ClassificationResult | Intents, product, urgency, risk flags with evidence + confidence | `schemas/classification_result.schema.json` |
| ExtractionResult | Entities and document types with provenance and validation | `schemas/extraction_result.schema.json` |
| RoutingDecision | Deterministic queue/SLA/actions decision with rule version | `schemas/routing_decision.schema.json` |
| AuditEvent | Append-only event log per stage with hashes + versions | `schemas/audit_event.schema.json` |

## Versioning rules

- Each schema has a SemVer `$id` URN and a `schema_version` field in instances.
- A schema **minor** version may add optional fields or relax constraints.
- A schema **major** version introduces breaking changes (field removal, meaning changes).
- All pipeline stage outputs must be schema-validated before persistence.

## Provenance and evidence

- Evidence spans reference canonicalized text sources and store only redacted snippets plus snippet hashes.
- Entity provenance includes source, offsets, and attachment identifiers.

## Immutability

- Raw inputs and audit events are append-only.
- Derived results in the normalized store are written as new versioned records rather than overwriting prior outputs.

## Canonical hashing

- Hashing uses the algorithm defined in `spec/00_CANONICAL.md`.
- `spec/07_AUDIT_GOVERNANCE.md` defines `decision_hash` and canonicalization rules.
