# IEIM Pack — SPEC (high level)

This file is a short map to the authoritative specifications in `spec/`.

## Start here

1. **SSOT**: `spec/00_CANONICAL.md`
2. Scope: `spec/01_SCOPE.md`
3. Architecture: `spec/02_ARCHITECTURE.md`
4. Data model and schemas: `spec/03_DATA_MODEL.md` and `schemas/`
5. Identity resolution: `spec/04_IDENTITY_RESOLUTION.md`
6. Classification and LLM gating: `spec/05_CLASSIFICATION_AND_LLM.md` and `prompts/`
7. Deterministic routing: `spec/06_ROUTING_RULES.md` and `configs/routing_tables/`
8. Audit and governance: `spec/07_AUDIT_GOVERNANCE.md`
9. Security and privacy: `spec/08_SECURITY_PRIVACY.md`
10. Phase plan: `spec/09_PHASE_PLAN.md`
11. Test strategy: `spec/10_TEST_STRATEGY.md` and `tests/`
12. Operations: `spec/11_OPERATIONS_RUNBOOK.md` and `runbooks/`

## Implementation contracts

- All inter-stage outputs are validated against JSON Schemas in `schemas/`.
- Canonical label-sets are defined once in `spec/00_CANONICAL.md` and enforced by `scripts/check_label_consistency.py`.
- Routing behavior is defined by the versioned routing table in `configs/routing_tables/`.

## Pack verification

Run:

```bash
bash scripts/verify_pack.sh
```

This pack is designed for deterministic, fail-closed enterprise implementation.
