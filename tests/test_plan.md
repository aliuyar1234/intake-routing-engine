# Test plan

This plan defines unit, integration, and end-to-end tests for IEIM.

Targets:
- Critical correctness: identity association and deterministic routing
- Safety: fail-closed behavior under ambiguity
- Auditability: every stage emits immutable, schema-valid audit events
- Determinism: replay yields identical decision hashes when versions match

## Unit tests

- Normalization
  - MIME parsing produces canonical subject/body
  - Message fingerprint stable for same content
- Attachment processing
  - AV status enforcements block infected items
  - Hashing is stable (SHA-256)
- Identity resolution
  - Scoring logic produces Top-K ranking
  - Tie and near-tie triggers review status
  - Evidence spans are present and offsets are valid
- Classification
  - Rule-based labels fire only on high-precision patterns
  - Disagreement gate triggers review for high-impact categories
  - Label outputs are restricted to canonical label sets
- Extraction
  - Entity validators reject malformed identifiers
  - Provenance references valid source offsets and attachment IDs
- Routing
  - Overrides (security/legal/GDPR/fraud) have priority
  - No-rule-match fails closed to general review
  - Output actions are restricted to canonical action strings
- decision hash
  - Hash excludes volatile fields and is stable for identical inputs

## Integration tests

- Ingestion adapters (stubs)
  - M365 Graph
  - IMAP
  - SMTP gateway
- Raw store
  - Append-only writes
  - Idempotency keys prevent duplicate derived outputs
- Case adapter (stub)
  - Idempotent create/update
  - Draft artifact attachment support

## End-to-end (E2E) tests

- Golden corpus regression
  - Execute `tests/e2e_spec.md` against `data/samples/`
  - Compare outputs to `data/samples/gold/` for identity, classification, extraction, routing
  - Verify audit event stage sequence and schema validity

## Replay/reprocess tests

- Deterministic replay
  - Using the same raw artifacts and the same versions, replay produces identical `decision_hash` values for identity and routing stages
  - Replay never overwrites prior derived outputs (new versioned records only)
  - Replay never triggers downstream side effects by default (case adapter not called unless explicitly and operationally approved)

## Coverage goals

- Unit tests: cover all deterministic scoring and routing branches
- Integration tests: cover all adapters with stubs
- E2E tests: cover the full sample corpus

## CI gates

- `bash scripts/verify_pack.sh` must pass
- All unit/integration/E2E tests must pass for the phase gate being claimed
