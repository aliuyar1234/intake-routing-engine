# Identity resolution

Identity resolution assigns an inbound email to the most likely **customer**, **policy**, or **claim** while remaining strictly **fail-closed**. The output is a Top-K ranking with evidence, signals, and confidence.

Canonical identity statuses and entity types are defined in `spec/00_CANONICAL.md`.

## Inputs

- `NormalizedMessage` (subject/body, sender recipients, thread metadata)
- `AttachmentArtifact` extracted text (if available and clean)
- Authoritative lookup adapters (CRM/Policy/Claims), read-only

## Outputs

- `IdentityResolutionResult` (Top-K candidates + evidence + confidence + status)

## Signal catalog

All signals are logged (signal name, value, weight) and must be deterministic. The concrete weights live in `configs/dev.yaml` and `configs/prod.yaml`.

### Hard-evidence signals

- Claim number found and validated by claims lookup
- Policy number found and validated by policy lookup
- Thread linkage to an existing case/claim
- Customer number found and validated by CRM

### Medium-evidence signals

- Sender email matches a CRM contact
- Name + postal code/address extracted from signature and matches CRM (deterministic fuzzy match)
- Valid identifiers found in attachment text and validated by lookup

### Soft-evidence signals

- Display name similarity to a known customer name
- Broker domain context (acts as an intermediary indicator)
- Shared mailbox heuristic penalty (reduces trust in sender email)

## Candidate retrieval

1. Extract identifiers from canonicalized subject/body and attachment text.
2. Validate identifiers using authoritative lookups.
3. Use thread keys (message-id, in-reply-to, conversation id) to retrieve linked cases.
4. Combine all retrieved entities into a candidate pool.

## Deterministic scoring

Each candidate receives a score in `[0,1]` computed deterministically from signal weights:

```text
score_raw = sum(weight_i * strength_i)
score = min(1.0, score_raw)

strength(HARD)=1.0
strength(MEDIUM)=0.7
strength(SOFT)=0.3

Shared mailbox penalty reduces score_raw before clamping.
```

Tie-breakers are deterministic and are applied in this order:
1. Candidates with hard evidence outrank those without.
2. If the email is claim-related, claims outrank policies; otherwise policies outrank customers.
3. Active/open entities outrank inactive/closed (from authoritative status).
4. A minimum score margin is required for automatic selection.

## Thresholding and fail-closed status

Identity status is derived from `(top_score, margin, presence_of_hard_evidence)`.

- Confirmed: minimum score and margin satisfied and at least one hard-evidence signal exists.
- Probable: relaxed thresholds, still requires a margin, and at least one medium-evidence signal.
- Needs review: any ambiguity, ties, insufficient margin, or reliance on soft signals.
- No candidate: candidate pool is empty.

The exact thresholds are configuration-driven and must be recorded in audit events via the referenced config hash.

## Broker and shared mailbox handling

- Broker mail is treated as intermediary context; it does not automatically confirm identity unless a validated policy or claim identifier exists.
- Shared mailboxes reduce confidence. Without validated identifiers, identity must be marked for review.

## Request additional information (approval-gated draft)

When identity is not safely resolvable, IEIM generates a request-info draft that asks only for minimal data required for safe routing:

- Preferred: claim number or policy number
- If unavailable: policyholder name and postal code

Draft templates are stored in `configs/templates/` and must never be sent automatically.

## Audit requirements

- The identity stage must emit an `AuditEvent` that includes:
  - input/output hashes
  - signal list and selected thresholds (via config hash)
  - evidence references (redacted snippets + snippet hashes)
  - decision hash (timestamp-free)
