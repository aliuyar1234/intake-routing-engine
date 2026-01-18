# End-to-end (E2E) specification

This E2E spec describes the deterministic reference pipeline behavior for the sample corpus.

## Inputs

- `data/samples/emails/*.json` (NormalizedMessage instances)
- `data/samples/attachments/*.artifact.json` (AttachmentArtifact instances)
- Routing ruleset: `configs/routing_tables/routing_rules_v1.4.1.json`

## Expected outputs

For each input message `<name>.json` there are gold outputs:
- `<name>.identity.json`
- `<name>.classification.json`
- `<name>.extraction.json`
- `<name>.routing.json`
- `<name>.audit_expectations.json`

## Deterministic pipeline steps

1. Read and validate the `NormalizedMessage` against `schemas/normalized_message.schema.json`.
2. Load attachment artifacts referenced by `attachment_ids` and validate each against `schemas/attachment_artifact.schema.json`.
3. Run identity resolution in determinism mode and validate output against `schemas/identity_resolution_result.schema.json`.
4. Run classification and extraction in determinism mode (rules + deterministic model); validate against schemas.
5. Run routing rules against the routing ruleset; validate against `schemas/routing_decision.schema.json`.
6. Emit `AuditEvent` records for each stage and verify the expected stage list.

## Comparison rules

- Outputs must match gold for all required fields.
- If a change is intended, it requires:
  - ruleset version bump, and
  - decision record update in `DECISIONS.md`, and
  - updated gold corpus.
