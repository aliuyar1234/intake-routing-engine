# Enterprise defaults (P9+)

This document records the **explicit default choices** for turning this repository from an SSOT pack + reference implementation into an **enterprise-ready, installable open-source system**.

These defaults are binding for phases **P9–P16** (see `spec/09_PHASE_PLAN.md` and `spec/13_ENTERPRISE_PHASE_PLAN_P9_PLUS.md`).

Notes:
- Canonical labels/IDs remain defined only in `spec/00_CANONICAL.md`.
- Security posture remains fail-closed: uncertainty routes to HITL/review or request-info, never silent auto-actions.

## Distribution and deployment

Ship both install paths with clear roles:

- **Primary “getting started” + single-node install:** Docker Compose
- **Primary enterprise production install:** Kubernetes + Helm

Profiles:
- Compose ships `starter` (single node, all dependencies bundled) and `production` (hardened, supports external dependencies).
- Helm ships one chart with values profiles `starter` and `production`.

## Infrastructure defaults

Baseline (enterprise-ready v1):
- **Object storage API:** S3-compatible
  - Starter: **MinIO** bundled
  - Production: any S3-compatible service (AWS S3 or an enterprise S3 appliance)
- **Database:** **PostgreSQL** (required)
  - Stores metadata and indexes (not raw bytes)
- **Queue/broker:** **RabbitMQ** (required)
- **Search/index:** not required by default
  - Use PostgreSQL indexes and PostgreSQL full-text search for basic UI query needs
  - OpenSearch can be added later if advanced search becomes a requirement

## Authentication, authorization, and secrets

Defaults:
- **OIDC baseline**
  - Starter: bundle **Keycloak** (preconfigured realm/client/roles)
  - Production: support any OIDC provider; provide Azure AD setup docs as the recommended enterprise path
- **Multi-tenancy:** single-tenant (enterprise-ready v1)
- **Secrets management**
  - Starter (Compose): Docker secrets; environment variables for non-secrets
  - Production (Helm): Kubernetes Secrets (document External Secrets Operator as an optional upgrade)
- **Transport security**
  - TLS at ingress is mandatory
  - mTLS between services is optional (via service mesh) and documented as a hardening option

RBAC requirements:
- RBAC must be enforced at the API boundary using OIDC JWT claims and the configured role mappings.
- Visibility of raw MIME and raw attachments is gated behind explicit permission (for example `can_view_raw`).

## Integrations shipped as first-class

Baseline integrations to be implemented for a “complete system” install:

- **Mail ingestion primary baseline:** Microsoft 365 Graph (incremental sync via delta query)
- **Secondary ingest adapters:** IMAP and SMTP gateway (supported but not the baseline)
- **Case/ticket adapter shipped first-class:** ServiceNow
- **Identity data source baseline:** a generic REST Identity Directory adapter, plus an example stub implementation
  - Identity scoring remains deterministic in IEIM; the directory provides candidates/signals.

## HITL experience

Ship a minimal web UI by default:
- Implement a thin, server-rendered UI embedded into the API service (no separate UI container).
- UI uses the canonical Review API contract and is not a separate source of truth.
- UI supports: queue list, item list, item detail with evidence, submit correction, approve/reject drafts.
- All UI actions are subject to the same RBAC and audit logging as API calls.

## Observability and operations

Defaults:
- **Metrics:** Prometheus
- **Dashboards:** Grafana
- **Instrumentation:** OpenTelemetry SDK in API and worker
- **Logs:** structured JSON logs to stdout
- **Tracing backend:** optional (OTLP export can be enabled, but is not required for the default gate)

## Performance targets (Gate G-017)

Define two targets: starter (Compose) and production (Helm).

Starter (Compose) target:
- Sustained throughput: 500 emails/hour
- Attachment limits: up to 10 MB; up to 20% of emails with attachments
- End-to-end latency (excluding time waiting for human review)
  - median under 5 minutes
  - p99 under 30 minutes for attachment-heavy cases
- Fail-closed requirement: identity ambiguity must create a review item (no auto-association)

Production (Helm) target:
- Sustained throughput: 3000 emails/hour
- Attachment limits: up to 20 MB; up to 30% of emails with attachments
- End-to-end latency
  - median under 2 minutes for no-OCR path
  - median under 10 minutes for OCR path
- Critical quality (on the regression corpus and agreed enterprise acceptance set)
  - confirmed-identity mis-association rate below 0.1%
  - auto-route misroute rate below 0.5%
  - uncertainty must route to review or request-info (fail-closed)

## LLM policy default

Safety and portability default:
- LLM is **disabled by default** for both starter and production.
- Local provider (Ollama) and external providers can be enabled explicitly later with:
  - pinned prompts and versions
  - token budgets and daily caps
  - audit logging and caching

