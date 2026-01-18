# AGENTS - Codex Handoff Rules (IEIM Pack v1)

You are implementing IEIM from this pack.

## Non-negotiable rules

1. **No guessing**: if something needed for implementation is missing, record it in `BLOCKERS.md` and stop the affected task. Do not invent APIs, labels, or schema fields.
2. **Single Source of Truth (SSOT)**: canonical constants and label-sets are defined **only** in `spec/00_CANONICAL.md`. Use them; do not redefine them elsewhere.
3. **Fail-closed by default**: uncertainty -> review or request-info. Never silently mis-associate or misroute.
4. **Immutability**: raw emails/attachments are append-only; audit events are append-only with a hash chain.
5. **Determinism mode**: must be reproducible; decision hashes must be timestamp-free.
6. **Every pipeline stage emits audit events** with hashes, versions, and evidence spans.
7. **Quality gates are binding**: do not merge/ship without passing the gates in `QUALITY_GATES.md`.

## Work order

Follow `spec/09_PHASE_PLAN.md` in order. For each phase:

- Implement the tasks of the phase.
- Run the required tests.
- Pass the phase gate.

## How to handle BLOCKERS

- `BLOCKERS.md` must remain empty for a complete pack implementation.
- If a blocker appears during implementation, write:
  - What is missing
  - Why it blocks
  - The minimal required decision or artifact to unblock

## Verification

Run the pack self-checks from the repo root:

```bash
bash scripts/verify_pack.sh
```

These checks enforce:
- no unfinished markers
- SSOT single definition rule
- schema validity
- label consistency against canonical label-sets
- manifest completeness and correct file hashes
