# Approval gate policy

IEIM may generate **draft** responses and **draft** request-for-information messages. Drafts are never sent automatically.

## Required approvals

- Customer-facing drafts require approval by a user with `can_approve_drafts: true`.
- Drafts for privacy requests require approval by a privacy officer.
- Drafts for legal matters require approval by the legal queue workflow.

## Prohibited content

- Drafts must not include full bank account numbers, identity document numbers, or health details.
- Drafts must not promise coverage, acceptance, or payment.

## Audit

Every draft creation, modification, approval, or rejection must emit an audit event (stage: HITL) that references the draft hash and approver identity.
