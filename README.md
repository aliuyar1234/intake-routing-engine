# Intake Routing Engine v1.0.4

Intake Routing Engine is an **open-source, self-hosted email intake and routing system**. It ingests inbound emails (with attachments), extracts structured facts, applies deterministic routing, and creates auditable downstream actions (case/ticket, drafts, or human review) with an immutable audit trail.

It turns inbound emails (including attachments) into **auditable, deterministic operational outcomes**:
ingest -> normalize -> attachment processing -> identity resolution -> classify/extract -> deterministic routing -> case/ticket actions -> HITL review (when needed) -> immutable audit log.

## What you get

- Production-ready pipeline services (API, worker, scheduler) with fail-closed defaults.
- Docker Compose distributions (`starter` and `production`) and a Kubernetes Helm chart.
- Adapters and mocks for enterprise integration (mail ingest, identity directory, case/ticket).
- Human-in-the-loop (HITL) review API and minimal web UI.
- Binding quality gates, deterministic decision hashing, and an append-only audit hash chain.

This is not a hosted SaaS. You deploy it in your own environment (Compose or Kubernetes/Helm).

## Architecture

High-level pipeline and integration boundaries:

```mermaid
flowchart LR
  A["Mail Ingestion"] --> B["Raw Store (immutable)"]
  B --> C["Normalize"]
  C --> D["Attachment Processing"]
  D --> E["Identity Resolution"]
  E --> F["Classification (rules/model/LLM gated)"]
  F --> G["Extraction"]
  G --> H["Routing Engine (deterministic)"]
  H --> I["Case/Ticket Adapter"]
  H --> J["HITL Gate"]
  J -->|review| K["Review UI/API"]
  K --> H
  C --> L["Audit Store (hash chain)"]
  D --> L
  E --> L
  F --> L
  G --> L
  H --> L
  I --> L
  K --> L
```

Details: `spec/02_ARCHITECTURE.md`

## Quickstart

From the repo root:

```bash
bash scripts/verify_pack.sh
python -B -m unittest discover -s tests -p "test_*.py"
```

Run locally with Docker Compose (starter):

```bash
docker compose -f deploy/compose/starter/docker-compose.yml up -d --build
python ieimctl.py demo run --config configs/dev.yaml --samples data/samples
docker compose -f deploy/compose/starter/docker-compose.yml down -v
```

## Design principles (product and compliance)

- **Fail-closed by default**: uncertainty routes to review or request-info drafts.
- **Immutability**: raw MIME/attachments are append-only; audit events are append-only with a hash chain.
- **Determinism mode**: reproducible decisions; decision hashes are timestamp-free.
- **Canonical contracts**: canonical labels/IDs and schema IDs are defined in `spec/00_CANONICAL.md` and enforced in CI.
- **Human-in-the-loop (HITL)**: reviewer actions are stored as versioned correction records and audited.

## Repository map (where to look)

- Canonical IDs and labels: `spec/00_CANONICAL.md`
- Scope and requirements: `spec/01_SCOPE.md`
- Phase plan and gates: `spec/09_PHASE_PLAN.md` and `QUALITY_GATES.md`
- Enterprise-ready roadmap (P9+): `spec/13_ENTERPRISE_PHASE_PLAN_P9_PLUS.md`
- Enterprise defaults (P9+): `spec/14_ENTERPRISE_DEFAULTS.md`
- Contracts (JSON Schemas): `schemas/`
- Interfaces (adapters and HITL): `interfaces/`
- Prompts and strict JSON contracts: `prompts/`
- Runbooks: `runbooks/` and `spec/11_OPERATIONS_RUNBOOK.md`
- Reference implementation: `ieim/` and `ieimctl.py`
- Verification scripts: `scripts/`
- Sample corpus + gold expectations: `data/samples/`

## Install

- Docker Compose: `docs/INSTALL_COMPOSE.md`
- Kubernetes/Helm: `docs/INSTALL_HELM.md`
- Upgrade guidance: `docs/UPGRADE.md`

## Releases (installable artifacts)

Each GitHub Release publishes:

- Helm chart package (`ieim-<version>.tgz`)
- SBOMs (SPDX JSON) for the published container images
- Signed provenance (`provenance.json` + `provenance.sig` + `provenance.crt`)

Release container images are published to GHCR:

- `ghcr.io/<owner>/ieim-api:<version>`
- `ghcr.io/<owner>/ieim-worker:<version>`
- `ghcr.io/<owner>/ieim-scheduler:<version>`

Details and verification: `docs/RELEASES.md`

## LLM usage (policy-gated)

LLM calls are optional, are gated to preserve safety and reproducibility, and are disabled by default.

Details: `spec/05_CLASSIFICATION_AND_LLM.md`

## License

Apache-2.0 (see `LICENSE`).
