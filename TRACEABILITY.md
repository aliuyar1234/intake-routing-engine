# TRACEABILITY - FR/NFR -> Modules -> Tasks -> Tests/Gates

This matrix maps requirements to modules, implementation tasks, and binding gates/tests.

Authoritative sources:
- FR/NFR definitions: `spec/01_SCOPE.md`
- Tasks and phase sequence: `spec/09_PHASE_PLAN.md`
- Gates: `QUALITY_GATES.md`

## FR traceability

| FR ID | Module(s) | Task(s) | Gate/Test(s) |
|---|---|---|---|
| FR-001 Ingestion | MOD_INGEST, MOD_RAW_STORE | T-005, T-006, T-007, T-008, T-010 | G-002; ingestion adapter integration tests; E2E corpus (`tests/e2e_spec.md`) |
| FR-002 Raw storage immutability | MOD_RAW_STORE, MOD_AUDIT | T-008, T-031, T-038 | G-002; raw-store append-only tests; retention job verification; pack verify (`scripts/verify_pack.sh`) |
| FR-003 Normalization | MOD_NORMALIZE | T-009 | G-002; schema validation (`scripts/validate_schemas.py`); E2E corpus |
| FR-004 Attachment processing | MOD_ATTACHMENT, MOD_SECURITY | T-011..T-016 | G-003; AV enforcement tests; attachment schema validation |
| FR-005 Identity candidate retrieval | MOD_IDENTITY | T-017 | G-004; identity lookup integration tests |
| FR-006 Identity ranking and thresholds | MOD_IDENTITY | T-018 | G-004; identity scoring unit tests (tie/near-tie fail-closed); determinism tests |
| FR-007 Classification | MOD_CLASSIFY | T-021..T-024 | G-005; label-set enforcement (`scripts/check_label_consistency.py`); E2E corpus |
| FR-008 Entity extraction | MOD_EXTRACT, MOD_SECURITY | T-025, T-026 | G-005; provenance validation tests; sensitive-entity policy tests |
| FR-009 Request-for-information generation | MOD_IDENTITY, MOD_CASE_ADAPTER | T-020, T-029 | G-004; template rendering tests (`configs/templates/request_info_*.md`); E2E corpus |
| FR-010 Deterministic routing | MOD_ROUTE, MOD_RULES_REGISTRY | T-027, T-028 | G-006; routing unit tests (override precedence + no-rule-match); E2E corpus |
| FR-011 Case/ticket adapter | MOD_CASE_ADAPTER | T-029, T-030 | G-006; adapter idempotency integration tests |
| FR-012 Draft reply creation | MOD_ROUTE, MOD_CASE_ADAPTER | T-027, T-029 | G-006; approval-gate policy tests (`configs/templates/approval_gate_policy.md`) |
| FR-013 HITL review | MOD_HITL_UI | T-035 | G-008; HITL workflow integration tests |
| FR-014 Feedback capture | MOD_HITL_UI, MOD_RULES_REGISTRY, MOD_AUDIT | T-036, T-037 | G-008; feedback record validation tests; governance checks |
| FR-015 Audit events | MOD_AUDIT | T-031..T-033 | G-007; audit schema validation; hash-chain verify tests |
| FR-016 Reprocessing | MOD_AUDIT, MOD_RULES_REGISTRY | T-032, T-033 | G-007; determinism replay tests; reprocess command tests |
| FR-017 Ruleset change management | MOD_RULES_REGISTRY | T-028, T-037 | G-001 (pack verify) + G-006 (routing regression); rules lint/sim tests |
| FR-018 Observability | MOD_OBSERVABILITY | T-034, T-038 | G-007 + G-009; metrics/log correlation tests; dashboards present |

## NFR traceability

| NFR ID | Module(s) | Task(s) | Gate/Test(s) |
|---|---|---|---|
| NFR-001 Reliability | Core, MOD_OBSERVABILITY | T-010, T-034, T-038, T-040 | G-009; load tests; incident drills; retry/idempotency tests |
| NFR-002 Performance | MOD_ROUTE, MOD_OBSERVABILITY | T-027, T-040 | G-009; routing latency benchmarks; throughput load tests |
| NFR-003 Security | MOD_SECURITY, MOD_ATTACHMENT | T-012, T-038, T-039 | G-003; AV enforcement tests; key rotation runbook verification |
| NFR-004 Privacy | MOD_SECURITY, MOD_AUDIT, MOD_CLASSIFY | T-023, T-026, T-031 | G-007; audit minimization checks; redaction tests |
| NFR-005 Compliance and retention | MOD_SECURITY, MOD_AUDIT | T-038 | G-009; retention job tests; access review process check |
| NFR-006 Audit integrity | MOD_AUDIT | T-031..T-033 | G-007; hash-chain verification tests |
| NFR-007 Operability | MOD_OBSERVABILITY, MOD_SECURITY | T-034, T-038, T-039 | G-009; runbook readiness review; on-call checklist |
| NFR-008 Cost control | MOD_CLASSIFY | T-023, T-024 | G-005; token budget unit tests; caching key tests |
| NFR-009 Maintainability | MOD_RULES_REGISTRY | T-001..T-004, T-028, T-037 | G-001; pack verify; schema backward-compat checks |
| NFR-010 Scalability | Core, MOD_OBSERVABILITY | T-040 | G-009; scaling/load validation report |
| NFR-011 Determinism and reproducibility | MOD_IDENTITY, MOD_ROUTE, MOD_AUDIT | T-018, T-027, T-032, T-033 | G-007; deterministic replay tests; decision_hash tests |
| NFR-012 Safety (fail-closed) | MOD_IDENTITY, MOD_ROUTE, MOD_SECURITY | T-018, T-024, T-027, T-030, T-039 | G-004..G-007; negative-case tests (ties, low confidence, no-rule-match, malware) |
