# Mail ingest adapter interface

This interface defines how IEIM ingests inbound emails.

## Required capabilities

- Fetch new messages with idempotent cursors
- Fetch raw MIME for each message
- Fetch attachment metadata and bytes
- Provide stable message identifiers from the source system

## Adapter contract

The adapter must produce:
- raw MIME bytes (stored immutably)
- source metadata required to populate NormalizedMessage fields

## Required metadata fields

- ingestion_source
- received_at
- from/to/cc
- thread keys (message-id, in-reply-to, conversation id)

## Error handling

- Transient failures are retried with backoff.
- Permanent failures produce an ingestion failure review item and emit audit events.
