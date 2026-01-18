# Audit and governance

IEIM is designed for full auditability and reproducibility.

Canonical pipeline stages and the audit schema `$id` are defined in `spec/00_CANONICAL.md`.

## Audit events per stage

Each pipeline stage must emit an `AuditEvent` that contains:
- stage identifier
- input hash and output hash
- decision hash (for decision-making stages)
- rule versions and model/prompt versions used
- evidence references (redacted snippets + snippet hashes)
- hash chain fields for tamper evidence

AuditEvents are append-only.

### Minimal required stages

The system emits at least these stages for a successful end-to-end run:
- ingestion
- normalization
- attachment processing
- identity
- classification
- extraction
- routing
- case adapter

## Hash chain integrity

The audit store maintains a per message-run hash chain:
- `prev_event_hash` references the previous event in the chain
- `event_hash` is the hash of the canonical JSON form of the current event

The chain is verified by `scripts/verify_pack.sh` (schema validation) and operationally by a periodic job (`ieimctl audit verify`).

## decision_hash (timestamp-free)

A decision hash is computed for decision stages (identity and routing at minimum). The goal is that the same inputs under the same config yield the same decision hash.

Definition:

```text
decision_hash = sha256( RFC8785_JSON(canonical_decision_input) )
```

The canonical decision input must include:
- system ID
- canonical spec semver
- message fingerprint
- hashes of relevant upstream outputs
- ruleset hash and version
- model and prompt identifiers (if used)
- determinism mode flag

The canonical decision input must not include any wall-clock timestamps.

Explicit exclusions (never included in canonical_decision_input):
- run_id
- ingested_at, received_at, occurred_at, or any other timestamps
- audit_event_id or event_hash values
- volatile execution identifiers (request IDs, worker IDs, hostnames)
- random seeds or non-deterministic sampling parameters

## Canonicalization rules

- Subject and body canonicalization is performed during normalization.
- Attachment ordering is canonicalized by `(sha256, filename)`.
- JSON canonicalization uses RFC8785.

## Governance for changes

- Ruleset changes require approval and regression simulation.
- Model/prompt changes require pinned versions, offline evaluation, and explicit promotion.
- Any deployed change must be recorded as an audit event in the operational system.

## Audit data minimization

Audit logs must not contain full sensitive values. Evidence uses redacted snippets and hashes. Full raw data remains in the raw store and is protected by RBAC.
