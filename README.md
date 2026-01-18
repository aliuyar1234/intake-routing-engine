# Insurance Email Input Manager (IEIM) — SSOT Pack v1.0.1

This repository is a **Single Source of Truth (SSOT) pack** for implementing the Insurance Email Input Manager (IEIM) as a production system. It combines specifications, schemas, configs, tests, and runbooks into a phase-by-phase delivery plan with binding quality gates.

IEIM’s objective is to turn inbound insurance emails (including attachments) into **auditable, deterministic operational outcomes**:
ingest → normalize → attachment processing → identity resolution → classify/extract → deterministic routing → case/ticket actions → HITL review (when needed) → immutable audit log.

## What this pack is (and is not)

- This is an **implementation handoff pack**: stable contracts, rules, and verification to build against.
- This is not a hosted service by itself. The included Python code is a **reference implementation** for local execution and verification of the contracts and gates.

## Architecture

High-level pipeline and integration boundaries:

```mermaid
flowchart LR
  A[Mail Ingestion] --> B[Raw Store (immutable)]
  B --> C[Normalize]
  C --> D[Attachment Processing]
  D --> E[Identity Resolution]
  E --> F[Classification (rules/model/LLM gated)]
  F --> G[Extraction]
  G --> H[Routing Engine (deterministic)]
  H --> I[Case/Ticket Adapter]
  H --> J[HITL Gate]
  J -->|review| K[Review UI/API]
  K --> H
  C --> L[Audit Store (hash chain)]
  D --> L
  E --> L
  F --> L
  G --> L
  H --> L
  I --> L
  K --> L
```

Details: `spec/02_ARCHITECTURE.md`

## Design principles (product and compliance)

- **Fail-closed by default**: uncertainty routes to review or request-info drafts.
- **Immutability**: raw MIME/attachments are append-only; audit events are append-only with a hash chain.
- **Determinism mode**: reproducible decisions; decision hashes are timestamp-free.
- **Single Definition Rule**: canonical labels/IDs are defined only in `spec/00_CANONICAL.md`.
- **Human-in-the-loop (HITL)**: reviewer actions are stored as versioned correction records and audited.

## Repository map (where to look)

- SSOT and labels: `spec/00_CANONICAL.md`
- Scope and requirements: `spec/01_SCOPE.md`
- Phase plan and gates: `spec/09_PHASE_PLAN.md` and `QUALITY_GATES.md`
- Contracts (JSON Schemas): `schemas/`
- Interfaces (adapters and HITL): `interfaces/`
- Prompts and strict JSON contracts: `prompts/`
- Runbooks: `runbooks/` and `spec/11_OPERATIONS_RUNBOOK.md`
- Reference implementation: `ieim/` and `ieimctl.py`
- Verification scripts: `scripts/`
- Sample corpus + gold expectations: `data/samples/`

## Quickstart (verification)

From the repo root:

```bash
bash scripts/verify_pack.sh
python -B -m unittest discover -s tests -p "test_*.py"
```

The CLI also exposes:

```bash
python ieimctl.py pack verify
```

## Configuration and operations

- **Incident toggles** (force review, disable LLM, block case creation for selected risk flags): `configs/prod.yaml` and `runbooks/incident_response.md`
- **Retention job** (file-backed reference): `python ieimctl.py retention run --help` and `runbooks/retention_jobs.md`
- **Load test harness** (file-backed sample corpus): `python ieimctl.py loadtest run --help`
  - Example report: `reports/load_test_report.json`

## LLM usage (policy-gated)

LLM calls are optional and are gated to preserve safety and reproducibility. The reference implementation supports:

- External provider (OpenAI) when enabled
- Local provider via Ollama for on-prem deployments

Details: `spec/05_CLASSIFICATION_AND_LLM.md`

## License

Apache-2.0 (see `LICENSE`).
