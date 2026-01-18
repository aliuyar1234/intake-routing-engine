# Architecture decision records (summary)

This file captures a subset of architectural decisions that drive implementation.

## ADR-001 — Default language choice

Decision: Use Python as the default implementation language for v1.

Rationale:
- Fast iteration for schema-driven pipelines and validation logic
- Strong ecosystem for email parsing, NLP, and integrations
- Hiring availability

Tradeoffs:
- Lower raw throughput than Rust/Go for CPU-heavy OCR; addressed by isolating OCR into a separate worker pool and allowing future extension points.

Extension points:
- Implement OCR and AV scanning adapters in Go or Rust if required for throughput
- Implement high-throughput message canonicalization in Rust if profiling justifies it

## ADR-002 — Deterministic routing engine

Decision: Use a versioned decision table and deterministic evaluation (first-match by priority), with risk overrides.

Rationale:
- Predictability and auditability
- Safe fail-closed behavior

## ADR-003 — Immutable audit store with hash chain

Decision: Use append-only audit events with per-event hash and previous-event hash.

Rationale:
- Tamper-evident auditing and reproducibility
