# Case/ticket system adapter interface

This interface defines how IEIM creates or updates a case/ticket in a downstream system.

## Required operations

- create_case
- update_case
- attach_artifact (raw email, attachments)
- add_note
- add_draft_message (approval-gated)

## Idempotency

Each create/update call must include an idempotency key derived from:
- message_fingerprint
- routing rule id + version
- adapter operation type

The adapter must not create duplicates when retried.

## Error handling

- Any adapter error must emit an audit event.
- Permanent failures route to the case create failure review queue.
