# Security, privacy, and compliance

This specification defines the baseline security and privacy controls for IEIM.

Canonical role and queue identifiers are defined in `spec/00_CANONICAL.md` where relevant.

## RBAC

Minimum roles:
- agent
- reviewer
- privacy officer
- security officer
- administrator

RBAC must enforce:
- access to raw MIME and attachments
- access to sensitive extracted entities (such as bank details)
- visibility of audit data

## Encryption

- In transit: TLS for all external and internal service calls
- At rest: object storage encryption, database encryption, and key management with rotation

## Retention

Retention is configuration-driven and must be technically enforced via lifecycle rules and DB partition/TTL policies.

## Audit logging policy

- Audit events contain hashes, versions, and redacted evidence snippets.
- Audit must not include full bank account numbers or identity document details.

## External LLM

If external LLM is enabled, all requests must be minimized and redacted. Attachments must not be sent externally.

## Access review

- Periodic access reviews are required.
- Break-glass access must be audited and time-limited.
