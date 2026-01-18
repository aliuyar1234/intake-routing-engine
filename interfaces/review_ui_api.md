# Review UI/API interface (HITL)

This interface defines the minimum contract for a Human-in-the-Loop (HITL) Review UI/API.

The Review UI must allow a reviewer to inspect the end-to-end pipeline outputs (with evidence) and record reviewer actions as immutable, audit-linked correction records.

Canonical identifiers (queues, stages) are defined in `spec/00_CANONICAL.md`.

## Required operations

The UI/API must support these operations:

- list review items for a given `queue_id`
- fetch a single review item (including evidence and references to stage outputs)
- submit corrections (identity/classification/routing)
- approve or reject drafts (request-info / reply) when policy requires approvals

All reviewer actions must emit an audit event (stage: HITL) and must never silently override system outputs.

## Review item shape (conceptual)

A review item represents a single `message_id` + `run_id` and references all relevant artifacts.

Minimum fields:

- review_item_id (stable identifier)
- message_id
- run_id
- queue_id
- created_at
- status (for example: OPEN, RESOLVED)
- artifact_refs (references to normalized message, identity result, classification result, extraction result, routing decision, drafts)
- evidence (redacted snippets + snippet hashes)

The Review UI should treat referenced artifacts as immutable snapshots.

## Correction submission

Submitting a correction must create a versioned CorrectionRecord that includes:

- stable correction_id
- reviewer identity (actor_type, actor_id)
- linkage to message_id/run_id (and optionally review_item_id)
- the corrected values expressed as a patch (for offline replay and evaluation)
- references to the affected artifacts (schema_id, uri, sha256)

Correction records must be stored append-only and referenced by the HITL audit event output hash.

## Draft approvals

If policy requires approvals (see `configs/templates/approval_gate_policy.md`):

- the UI must support approve/reject actions per draft artifact
- each approve/reject action must be recorded as a correction record and audited (stage: HITL)

Draft approvals must not auto-send external communications.

## RBAC requirements

The UI/API must enforce:

- reviewers without raw access cannot view raw MIME or attachments
- only users with `can_approve_drafts: true` can approve customer-facing drafts
- privacy officer approval is required for privacy/DSR drafts

All access and actions should be audit logged in the operational system.

