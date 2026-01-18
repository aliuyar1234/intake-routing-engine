# Internal event contracts (optional)

IEIM can emit internal events for observability and downstream integrations. This is optional; the default implementation requires only the immutable audit log.

## Event envelope

- event_id
- event_type
- occurred_at
- message_id
- run_id
- payload

## Core event types

- ieim.message.ingested
- ieim.message.normalized
- ieim.attachments.processed
- ieim.identity.completed
- ieim.classification.completed
- ieim.extraction.completed
- ieim.routing.completed
- ieim.case.completed
- ieim.hitl.reviewed
