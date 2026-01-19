# IEIM Enterprise-Ready Phase Plan (P9+) — Codex Implementation Guide

**Repo:** Intake Routing Engine v1.0.5  
**Goal:** Extend the existing DONE/PASSED phases (P0–P8) into an **installable, operable, enterprise-ready open-source system**.  
**Non‑negotiables:** fail‑closed default, SSOT canonical definitions in `spec/00_CANONICAL.md`, append‑only raw + audit stores, deterministic decision hashing (timestamp‑free), audit events for every stage, binding quality gates, strict unfinished‑marker scanning.

This document is written so Codex can implement **without inventing contracts**. Where decisions are required, the questions are enumerated up front with viable options and the phase plan shows how work branches.

---

## Decisions locked

The required enterprise defaults are now decided and recorded in `spec/14_ENTERPRISE_DEFAULTS.md` (see DR-008 in `DECISIONS.md`).

Section 0 is retained for background/context; treat the defaults in `spec/14_ENTERPRISE_DEFAULTS.md` as binding for implementation.

## 0) Required decisions and questions (must be answered before starting P9)

These are the remaining open decisions that prevent a “plug‑and‑play” enterprise install from being defined without assumptions. Answering them converts uncertainty into explicit requirements and prevents drift.

### A) Deployment target and distribution

**A1. Default install path (distribution): choose 1 primary, optionally ship the other**
- Option A: Docker Compose as primary install path  
  **Pros:** easiest onboarding, single-node starter profile, minimal cluster knowledge  
  **Cons:** not HA by default, enterprises often want Kubernetes
- Option B: Kubernetes + Helm as primary install path  
  **Pros:** HA patterns, enterprise standard, better scaling story  
  **Cons:** higher barrier to entry, harder local demo
- Option C: Dual-first: ship both as first-class with equal gates  
  **Pros:** satisfies both audiences  
  **Cons:** more work; more surface area to maintain

**A2. OS support**
- Option A: Linux runtime only; Windows supported for development via WSL2  
- Option B: Linux runtime plus native Windows runtime for single-node (Compose) installs  
- Option C: Linux only, including dev

**A3. Deployment profiles**
- Option A: “starter” single node only  
- Option B: “starter” plus “production” HA profiles (recommended for enterprise readiness)  
- Option C: “production” HA only

### B) Persistence and infrastructure defaults

**B1. Object storage (raw MIME + attachments + derived artifacts)**
- Option A: S3-compatible API as the core abstraction, ship MinIO for starter  
  **Pros:** portable across clouds, simple abstraction  
  **Cons:** enterprise may require cloud-native identity controls
- Option B: Cloud-native first (Azure Blob or AWS S3) with MinIO optional  
  **Pros:** aligns with managed services  
  **Cons:** reduces out-of-box local install parity
- Option C: File-backed only for starter, object storage required for production  
  **Pros:** minimal starter dependencies  
  **Cons:** larger migration gap to production

**B2. Database for metadata, review items, audit indexes**
- Option A: Postgres as default and required for production  
- Option B: Postgres default, allow MySQL/MariaDB as secondary  
- Option C: Postgres plus optional OpenSearch, no other SQL

**B3. Queue/broker**
- Option A: RabbitMQ  
  **Pros:** common, reliable, supports priority queues  
  **Cons:** extra operational component
- Option B: Redis Streams  
  **Pros:** simpler stack, fast  
  **Cons:** different durability semantics, enterprise acceptance varies
- Option C: Kafka  
  **Pros:** high throughput, enterprise standard in some orgs  
  **Cons:** heavier operational burden

**B4. Search/index**
- Option A: Postgres only (indexes + FTS)  
- Option B: Optional OpenSearch/Elasticsearch for UI search  
- Option C: Mandatory OpenSearch for enterprise

### C) AuthN/AuthZ and security posture

**C1. OIDC provider baseline**
- Option A: Keycloak shipped for starter; production supports any OIDC provider  
- Option B: Azure AD documented as primary; Keycloak optional for dev  
- Option C: No bundled provider; require enterprise OIDC

**C2. Multi-tenant separation**
- Option A: Single-tenant only (recommended initial enterprise deploy for internal ops teams)  
- Option B: Soft multi-tenant (tenant_id scoping in DB and RBAC)  
- Option C: Hard multi-tenant (separate DB buckets per tenant)

**C3. Secrets management**
- Option A: Environment variables and container secrets for starter; Kubernetes secrets for production  
- Option B: Add HashiCorp Vault integration as default for production  
- Option C: Cloud key vault integration as default (Azure Key Vault or AWS KMS/Secrets Manager)

**C4. Service-to-service encryption**
- Option A: TLS at ingress only, internal network trusted  
- Option B: mTLS between services (service mesh or app-level)  
- Option C: mTLS optional, documented as enterprise profile

### D) Integrations (system completeness requires at least one real adapter)

**D1. Mail ingestion baseline shipped out of the box**
- Option A: M365 Graph ingestion is mandatory (enterprise typical)  
- Option B: IMAP + SMTP are sufficient; M365 Graph is an additional adapter  
- Option C: All three are first-class and gated equally

**D2. Case/ticket adapter shipped first-class**
Choose at least one to be fully implemented and tested against a mock API:
- Option A: ServiceNow  
- Option B: Jira Service Management  
- Option C: Zendesk  
- Option D: Salesforce Service Cloud  
- Option E: Generic webhook adapter as the only first-class (not recommended if “complete” requires a named product)

**D3. Identity data source (customer/policy/claim lookup)**
- Option A: Ship a generic REST “identity directory” adapter with documented endpoint contract + example implementation  
- Option B: Ship an adapter for a known insurance core system (Guidewire, Duck Creek)  
- Option C: Do not ship real connector; require customer implementation (weakens plug‑and‑play)

### E) HITL UI and approval workflows

**E1. UI requirement**
- Option A: API-only is acceptable (customers build their UI)  
- Option B: A minimal web UI is required for enterprise-ready install (recommended if reviewers must work day one)

**E2. Approval workflow semantics**
- Who can approve drafts, and is two-person approval required for certain queues (privacy, legal)?
- Should approvals be mandatory for all drafts or only for reply drafts?

### F) LLM policy and on-prem posture

**F1. Default LLM mode**
- Option A: Disabled by default in all installs; can be enabled explicitly  
- Option B: Local provider enabled by default in starter (Ollama), external provider optional  
- Option C: Both disabled by default; provide guided enablement

**F2. Local models to support and test by default**
- Provide a small supported set (model name, quantization, minimal hardware).  
- Confirm whether Qwen2.5 Coder 7B Instruct is the required baseline.

**F3. Offline evaluation tooling**
- Is an offline evaluation CLI required for enterprise-ready, or is regression against sample corpus sufficient?

### G) Observability and operations

**G1. Telemetry stack**
- Option A: OpenTelemetry SDK + Prometheus metrics + Grafana dashboards  
- Option B: OpenTelemetry end-to-end including tracing to Tempo/Jaeger  
- Option C: Metrics only, no distributed tracing

**G2. SLOs and required dashboards**
- Define required SLOs and alerting rules for “enterprise-ready” acceptance.

**G3. Backup and disaster recovery**
- Define backup scope (DB, object storage, configs, audit) and RPO/RTO expectations.

### H) Compliance and data handling

**H1. Data residency**
- Single region only or multiple regions? Any cross-region replication restrictions?

**H2. Redaction and logging policy**
- Are there hard requirements to redact PII from application logs by default beyond current spec?

**H3. Audit retention**
- Required audit retention periods, and whether WORM storage is required.

### I) Performance and scaling targets

**I1. Throughput and latency**
- Average and peak emails per hour, attachment size distributions, acceptable end-to-end latency.

**I2. Worker sizing and concurrency**
- Baseline CPU and memory per worker, OCR and AV throughput expectations.

**Implementation rule:** Until these are answered, P9 tasks that depend on them must create a decision record and a repo-level configuration switch rather than guessing.

---

## 1) Minimal target architecture for “enterprise-ready install”

This is the smallest architecture that is still enterprise-safe and operable, while retaining the existing SSOT contracts and fail-closed behavior.

### 1.1 Required runtime components (default enterprise-safe)

1) **ieim-api** (HTTP)
- Exposes:
  - ingestion endpoints (SMTP gateway HTTP endpoint if used)
  - review UI API (`interfaces/review_ui_api.md`)
  - admin endpoints for health and readiness
- Enforces OIDC and RBAC for all non-health routes.

2) **ieim-worker**
- Consumes jobs from the broker.
- Executes pipeline stages:
  - ingest normalization (when queued)
  - attachment processing (AV/OCR)
  - identity resolution
  - classification and extraction (rules and optional model providers)
  - routing decision
  - case adapter invocation
  - HITL record creation and reprocess triggers

3) **ieim-scheduler**
- Runs periodic tasks:
  - mailbox polling (Graph/IMAP) if configured
  - retention enforcement
  - audit chain verification
  - dead-letter requeue policies

4) **Postgres** (metadata and indexes)
- Tables for:
  - message metadata, processing runs
  - review items, assignments, correction records index
  - audit event index (content remains append-only; stored as artifacts)
  - config snapshots and ruleset registry

5) **Object storage** (raw + derived artifacts)
- Buckets or prefixes:
  - raw MIME and raw attachments (append-only)
  - derived artifacts (normalized message, stage outputs, drafts, correction records)
  - audit events (append-only) and chain verification markers

6) **Broker**
- Durable queue for pipeline stage jobs.

7) **Auth provider (OIDC)**
- Starter can ship a local provider, production integrates with enterprise OIDC.

8) **Observability**
- Metrics endpoint (Prometheus scrape)
- Structured logs (JSON)
- OpenTelemetry traces if enabled

### 1.2 Optional components (do not affect default install behavior)

- OpenSearch/Elasticsearch: only if required for advanced search in UI
- DMS adapter: only if the customer wants document archiving beyond case system
- Service mesh (mTLS): only if required by enterprise security posture
- External LLM provider: optional; local provider optional; both gated and disabled until enabled

### 1.3 Non-negotiable data properties in the architecture

- Raw MIME and attachments are append-only and never overwritten.
- Audit events are append-only and linked by a hash chain.
- Correction records are immutable artifacts linked from audit events.
- Determinism mode produces timestamp-free decision hashes.
- Uncertainty routes to review or request-info drafts.

---

## 2) Migration strategy that preserves SSOT while adding production deployability

### 2.1 Repo structure additions (keeps SSOT verification intact)

Add production assets under dedicated folders, leaving `spec/` and `schemas/` as the canonical contracts:

- `deploy/compose/`  
  - `starter/` (single-node profile)  
  - `production/` (hardened profile, may still be single cluster)

- `deploy/helm/`  
  - Helm chart with values profiles and hardening defaults

- `infra/`  
  - SQL migrations, bootstrap scripts, backup scripts

- `docs/`  
  - installation, upgrade, operator guide (must pass unfinished-marker scan)

### 2.2 Keep SSOT stable

- Any canonical labels, IDs, schema URNs, and interface IDs remain defined only in `spec/00_CANONICAL.md`.
- Production code may reference canonical tokens but must not introduce new definitions outside the canonical file.
- If a new canonical token is required, update `spec/00_CANONICAL.md` and update all dependent validations and tests in the same change set.

### 2.3 Keep verification intact

- `MANIFEST.sha256` must include any new files added to the repository.
- `scripts/verify_pack.sh` remains the root gate and is extended to include new checks rather than bypassed.
- All new docs and manifests must avoid unfinished-work markers.

### 2.4 Backward compatibility policy

- Spec and schemas are stable contracts.
- Production changes that require schema changes must:
  - bump schema version
  - keep backward compatibility unless explicitly declared
  - update sample corpus and gold expectations

---

## 3) New phases after P0–P8 (P9+) with tasks and binding gates

**Numbering constraint:** tasks continue at T‑041, gates continue at G‑010.

### P9 — Production runtime packaging foundation (services, config, and persistence)

**Objective:** Convert the reference implementation into deployable long-running services with production-grade persistence abstractions while keeping existing file-backed mode for local verification.

**Tasks**
- **T-041: Service entrypoints and process model**
  - Deliverables:
    - `ieim/api/app.py` (API server entrypoint)
    - `ieim/worker/main.py` (worker entrypoint)
    - `ieim/scheduler/main.py` (scheduler entrypoint)
    - `ieim/runtime/health.py` (health/readiness)
  - Tests:
    - `tests/test_p9_service_entrypoints.py` starts each entrypoint in a dry-run mode.

- **T-042: Configuration layering and validation**
  - Deliverables:
    - `ieim/runtime/config.py` validates a config file via dataclass-backed loaders
    - `ieimctl.py config validate` command
  - Tests:
    - `tests/test_p9_config_validate_cli.py`

- **T-043: Production persistence adapters (interfaces only, one implementation chosen by decision B1/B2)**
  - Deliverables:
    - `ieim/store/object_store.py` interface (put/get, append-only contract)
    - `ieim/store/meta_store.py` interface (Postgres metadata)
    - implementation for selected stack:
      - S3-compatible object store adapter or file store remains dev-only
      - Postgres adapter with migrations
  - Tests:
    - `tests/test_p9_store_contracts.py` with local test containers or in-memory fakes

- **T-044: Broker interface and one concrete broker implementation (chosen by decision B3)**
  - Deliverables:
    - `ieim/broker/broker.py` interface
    - one implementation: RabbitMQ
    - dead-letter semantics and retry limits (fail-closed)
  - Tests:
    - `tests/test_p9_broker_contracts.py`

- **T-045: Deterministic job orchestration and idempotency**
  - Deliverables:
    - job IDs derived from message_id + stage + config hash + inputs hash
    - ensures replays do not duplicate artifacts
    - durable exactly-once effect at artifact level via idempotency checks
  - Tests:
    - `tests/test_idempotency_replay.py`

**Gate G-010 (binding): P9 integration readiness**
- Evidence:
  - Services start in local mode
  - Config validation works
  - Store and broker contracts pass unit tests
- Minimum commands:
  - `bash scripts/verify_pack.sh`
  - `python -B -m unittest discover -s tests -p "test_*.py"`
- Done when:
  - All commands exit with code 0
  - `ieimctl.py config validate --config configs/dev.yaml` exits 0
  - `ieimctl.py config validate --config configs/prod.yaml` exits 0

---

### P10 — Installable Docker Compose distribution (starter and production profiles)

**Objective:** Provide a concrete “install and run” experience using Docker Compose, including dependencies, secure defaults, and a functional demo flow.

**Tasks**
- **T-046: Docker images**
  - Deliverables:
    - `deploy/compose/Dockerfile.api`
    - `deploy/compose/Dockerfile.worker`
    - `deploy/compose/Dockerfile.scheduler`
    - multi-stage builds, non-root user, pinned base images
  - Tests:
    - `tests/test_container_smoke.py` (build + run minimal)

- **T-047: Compose starter profile**
  - Deliverables:
    - `deploy/compose/starter/docker-compose.yml`
    - includes:
      - api, worker, scheduler
      - Postgres, object store (MinIO), RabbitMQ, Keycloak (starter)
      - network isolation, only API port exposed
      - default config mounted read-only
  - Tests:
    - `tests/test_compose_starter_e2e.py` (spins up compose and runs a small ingest-run end-to-end)

- **T-048: Compose production-hardened profile**
  - Deliverables:
    - `deploy/compose/production/docker-compose.yml`
    - includes:
      - TLS termination option
      - externalized secrets via compose secrets
      - explicit retention job scheduling
      - resource limits and restart policies
  - Tests:
    - `tests/test_compose_production_smoke.py`

- **T-049: Install and operator docs**
  - Deliverables:
    - `docs/INSTALL_COMPOSE.md`
    - `docs/CONFIGURATION.md`
    - `docs/SECURITY_MODEL.md` (how OIDC and RBAC are configured)
  - Tests:
    - `scripts/check_placeholders.py` must pass on docs

**Gate G-011 (binding): Compose install and demo flow**
- Evidence:
  - Starter compose profile runs end-to-end on sample corpus
  - Production compose profile starts and exposes only intended ports
- Minimum commands:
  - `bash scripts/verify_pack.sh`
  - `python -B -m unittest discover -s tests -p "test_*.py"`
  - `docker compose -f deploy/compose/starter/docker-compose.yml up -d --build`
  - `python ieimctl.py demo run --config configs/dev.yaml --samples data/samples`
  - `docker compose -f deploy/compose/starter/docker-compose.yml down -v`
- Done when:
  - demo run completes and produces audit chain verification success
  - no container runs as root
  - no raw MIME is logged by default (validated via log scan test)

---

### P11 — Kubernetes and Helm distribution (enterprise install path)

**Objective:** Provide Kubernetes manifests and a Helm chart that supports secure production installs with externalized dependencies.

**Tasks**
- **T-050: Helm chart skeleton**
  - Deliverables:
    - `deploy/helm/ieim/Chart.yaml`
    - `deploy/helm/ieim/values.yaml`
    - templates for api, worker, scheduler deployments, service, ingress, config maps, secrets
    - k8s probes, resource requests/limits
  - Tests:
    - `tests/test_helm_template_render.py` renders templates and checks required fields

- **T-051: External dependency configuration**
  - Deliverables:
    - values to connect to external Postgres, external object store, external broker, external OIDC
    - optional embedded dependencies only in “starter” values
  - Tests:
    - values validation test

- **T-052: Operational jobs**
  - Deliverables:
    - CronJobs for retention and audit verification
    - optional mailbox polling as CronJob
  - Tests:
    - manifest linting test

- **T-053: Kubernetes install docs**
  - Deliverables:
    - `docs/INSTALL_HELM.md`
    - `docs/UPGRADE.md` with versioned migration steps
  - Tests:
    - docs scan passes

**Gate G-012 (binding): Helm install smoke test**
- Evidence:
  - Helm chart renders and installs into a local cluster profile
- Minimum commands:
  - `bash scripts/verify_pack.sh`
  - `python -B -m unittest discover -s tests -p "test_*.py"`
  - `helm template ieim deploy/helm/ieim -f deploy/helm/ieim/values.yaml`
- Done when:
  - template rendering produces valid manifests
  - chart enforces no privileged pods, non-root, read-only root filesystem where possible

---

### P12 — Enterprise authentication, RBAC hardening, and Review UI

**Objective:** Ensure the system is secure by default with OIDC + RBAC and provide a usable HITL experience.

**Tasks**
- **T-054: OIDC integration in API**
  - Deliverables:
    - JWT validation middleware
    - OIDC discovery and key rotation support
    - mapping from token roles to configured RBAC roles in `configs/*`
  - Tests:
    - `tests/test_auth_oidc_jwt_validation.py` with local test keys
    - `tests/test_rbac_matrix.py` validates allowed and denied operations against `interfaces/review_ui_api.md`

- **T-055: Review API implementation**
  - Deliverables:
    - Implement all required endpoints from `interfaces/review_ui_api.md`
    - ETag and idempotency enforcement
    - audit event emission for HITL actions
  - Tests:
    - `tests/test_review_api_contract.py` validates request/response shapes

- **T-056: Minimal web UI (server-rendered, embedded in API)**
  - Deliverables:
    - `ui/` (either single-page app or server-rendered pages)
    - login via OIDC
    - list items by queue, review details, submit correction, approve drafts
  - Tests:
    - `tests/test_ui_smoke.py` (headless smoke with API stubs)

**Gate G-013 (binding): Auth and HITL readiness**
- Evidence:
  - API endpoints enforce RBAC fail-closed
  - HITL actions create immutable correction records and audit events
- Minimum commands:
  - `bash scripts/verify_pack.sh`
  - `python -B -m unittest discover -s tests -p "test_*.py"`
- Done when:
  - Unauthorized access to any review endpoint yields 401
  - Unauthorized role access yields 403
  - Correction submission yields a correction record artifact ref and triggers deterministic reprocess

---

### P13 — Production integrations (mail ingest and case adapter)

**Objective:** Provide at least one complete mail ingest path and at least one complete case adapter that a company can use immediately.

**Tasks**
- **T-057: Mail ingestion hardening (Microsoft 365 Graph baseline; IMAP/SMTP supported)**
  - Deliverables:
    - M365 Graph: incremental sync, robust retry, token refresh, idempotent message ingestion
    - IMAP: safe polling, UID-based incremental fetch, loop protection
    - SMTP gateway: authenticated submission, rate limiting
  - Tests:
    - mock server integration tests for each adapter

- **T-058: Case adapter first-class implementation (ServiceNow)**
  - Deliverables:
    - implement chosen adapter fully
    - include mapping from routing actions to case system operations
    - failure behavior: fail-closed and route to `QUEUE_CASE_CREATE_FAILURE_REVIEW`
  - Tests:
    - mock API tests with deterministic fixtures

- **T-059: Generic REST identity directory adapter (required)**
  - Deliverables:
    - `interfaces/identity_directory_adapter.md` (if not already present)
    - implementation that queries customer/policy/claim by signals
  - Tests:
    - mock adapter tests and identity ranking regression

**Gate G-014 (binding): Integration readiness**
- Evidence:
  - At least one mail ingest adapter works end-to-end into the pipeline
  - At least one case adapter creates a case using a mock API and attaches artifacts
- Minimum commands:
  - `bash scripts/verify_pack.sh`
  - `python -B -m unittest discover -s tests -p "test_*.py"`
  - `python ieimctl.py ingest simulate --adapter <adapter> --samples data/samples`
  - `python ieimctl.py case simulate --adapter <adapter> --samples data/samples`
- Done when:
  - failures produce deterministic audit events and route to failure queues rather than silently dropping

---

### P14 — Observability, backups, retention, and operator experience

**Objective:** Provide the operational features required for enterprise readiness: monitoring, alerting, backups, and runbooks aligned with real deployments.

**Tasks**
- **T-060: Metrics and dashboards**
  - Deliverables:
    - Prometheus metrics endpoint for api and workers
    - Grafana dashboards as JSON under `deploy/observability/grafana/`
    - alert rules under `deploy/observability/prometheus/`
  - Tests:
    - `tests/test_metrics_exposed.py` validates key metrics exist

- **T-061: OpenTelemetry tracing**
  - Deliverables:
    - OTel instrumentation with trace correlation IDs in logs
  - Tests:
    - trace context propagation test

- **T-062: Backup and restore procedures**
  - Deliverables:
    - `infra/backup/backup.sh` and `infra/backup/restore.sh` with docs
    - covers Postgres, object store, config snapshots
  - Tests:
    - `tests/test_backup_restore_smoke.py` in compose environment

- **T-063: Retention enforcement in production**
  - Deliverables:
    - production retention job integrated into scheduler or k8s CronJob
    - evidence that raw and audit immutability are preserved
  - Tests:
    - retention tests against a seeded dataset

**Gate G-015 (binding): Operability gate**
- Evidence:
  - dashboards render, alerts rules are valid, backup/restore runs successfully in a test environment
- Minimum commands:
  - `bash scripts/verify_pack.sh`
  - `python -B -m unittest discover -s tests -p "test_*.py"`
  - `python ieimctl.py ops smoke --config configs/dev.yaml`
- Done when:
  - backup produces restorable artifacts and restore returns to a consistent state
  - retention job does not delete immutable audit chain records outside policy

---

### P15 — Release engineering, SBOM, signing, and upgrade path

**Objective:** Provide a repeatable release pipeline that produces versioned artifacts and upgrade guidance.

**Tasks**
- **T-064: Versioning and release metadata**
  - Deliverables:
    - `VERSION` file and consistent semver handling in `ieimctl.py`
    - changelog and upgrade notes structure under `docs/`
  - Tests:
    - version consistency unit test

- **T-065: Container build and publish pipeline**
  - Deliverables:
    - GitHub Actions workflow under `.github/workflows/`
    - builds images, tags with semver, pushes to container registry
  - Tests:
    - workflow linting test (static validation)

- **T-066: SBOM generation and signing**
  - Deliverables:
    - SBOM generation (SPDX or CycloneDX) stored as release artifact
    - image signing process with provenance
  - Tests:
    - `tests/test_sbom_presence.py` ensures CI artifacts exist in release mode

- **T-067: Database migrations and upgrade checks**
  - Deliverables:
    - migration tool invocation documented and enforced
    - upgrade check command `ieimctl.py upgrade check`
  - Tests:
    - migration forward and backward smoke on a temporary database

**Gate G-016 (binding): Release readiness**
- Evidence:
  - release pipeline builds artifacts and produces SBOM and signatures
  - upgrade docs exist and are consistent with migrations
- Minimum commands:
  - `bash scripts/verify_pack.sh`
  - `python -B -m unittest discover -s tests -p "test_*.py"`
  - `python ieimctl.py upgrade check --config configs/prod.yaml`
- Done when:
  - a tagged build produces images, chart package (if Helm), SBOM, and signed provenance
  - upgrade check fails closed if migrations are missing

---

### P16 — Performance, scaling, and enterprise acceptance benchmarks

**Objective:** Define and validate scaling targets and provide guidance for sizing and concurrency.

**Tasks**
- **T-068: Load test profiles and reports**
  - Deliverables:
    - extend load test harness to run against broker-backed runtime
    - produce structured report under `reports/`
  - Tests:
    - `tests/test_loadtest_report_schema.py`

- **T-069: Worker scaling guidance**
  - Deliverables:
    - docs for concurrency, max attachment size, OCR and AV worker separation
    - Kubernetes HPA values and suggestions if using Helm
  - Tests:
    - configuration validation tests

**Gate G-017 (binding): Performance gate**
- Evidence:
  - meets the throughput and latency targets defined in `spec/14_ENTERPRISE_DEFAULTS.md`
- Minimum commands:
  - `bash scripts/verify_pack.sh`
  - `python ieimctl.py loadtest run --profile enterprise_smoke --config configs/dev.yaml`
- Done when:
  - report shows achieved throughput and error budgets within targets
  - mis-association and misroute remain within defined thresholds and fail-closed behavior triggers HITL rather than silent errors

---

## 4) Release and distribution plan (enterprise install)

### 4.1 Versioning policy
- Semantic versioning for the repo release.
- Schemas have independent semver and are only bumped when schema changes occur.
- Routing rulesets and prompts have their own versions recorded in config and audit events.

### 4.2 Release artifacts
- Source tag and release notes
- Container images:
  - `ieim-api:<version>`
  - `ieim-worker:<version>`
  - `ieim-scheduler:<version>`
- Helm chart package:
  - `ieim-<version>.tgz` (if Helm enabled)
- SBOM artifact
- Signed provenance for images

### 4.3 Upgrade path
- Documented in `docs/UPGRADE.md`
- Database migrations are mandatory and checked by `ieimctl.py upgrade check`
- Rolling upgrades supported for workers where possible

### 4.4 CI/CD rules
- Every PR must pass:
  - pack verification
  - unit tests
  - regression against sample corpus
- Release builds add:
  - container builds
  - SBOM generation
  - signing and provenance

---

## 5) How Codex should implement this plan without guessing

1) Create a decision file capturing answers to Section 0 and link it from `DECISIONS.md`.  
2) Implement phases in order: P9 then P10, then P11, then P12, then P13, then P14, then P15, then P16.  
3) After each phase, implement the corresponding gate as an automated test or script and ensure it runs in CI.  
4) Do not introduce new canonical tokens outside `spec/00_CANONICAL.md`. If a token is needed, update canonical and update validators and tests in the same change set.  
5) Keep raw and audit stores append-only, and make replay deterministic with timestamp-free decision hashes.  
6) Ensure the sample corpus remains the regression baseline for routing, identity, audit, and HITL behavior.  
7) Keep the repository installable via the chosen distribution path and make documentation part of gates.
