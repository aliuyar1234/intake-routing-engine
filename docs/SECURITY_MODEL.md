# Security model

IEIM is designed as a fail-closed, auditable pipeline for regulated inbound communications.

## Core posture

- Fail-closed by default: uncertainty routes to HITL review or request-info drafts (never silent auto-actions).
- Raw and derived artifacts are treated as immutable (append-only). Audit events are append-only with a hash chain.
- Determinism: decision hashes are computed from timestamp-free inputs and versioned configuration references.

## Data access boundaries

Raw MIME and raw attachments are considered sensitive and are not meant to be broadly visible.

The RBAC model is configured via `configs/*.yaml` role mappings. At minimum:

- restrict raw MIME visibility behind an explicit permission (for example `can_view_raw`)
- ensure reviewers and privacy/security officers have auditable access paths

## Authentication and RBAC

The API enforces authentication and authorization at the boundary:

- All non-health API endpoints under `/api/` require a valid OIDC JWT and are RBAC-checked.
- The embedded Review UI under `/ui/` is protected by the same OIDC + RBAC checks.

OIDC and RBAC settings live in `configs/*.yaml`:

- `auth.oidc`: OIDC issuer, JWT validation, and optional direct-grant login enablement.
- `rbac.role_mappings`: map roles to permissions (`can_view_raw`, `can_view_audit`, `can_approve_drafts`).

Fail-closed default:

- Missing/invalid tokens yield `401`.
- Valid tokens without required permissions yield `403`.

## TLS and ingress

The production Compose profile terminates TLS at ingress using a reverse proxy. The default configuration uses a locally generated certificate (`tls internal`) and is intended for evaluation and internal testing. The default port is `8443`.

## LLM policy

LLM usage is disabled by default in both `configs/dev.yaml` and `configs/prod.yaml`. If enabled, LLM calls must be policy-gated, budgeted, and auditable.
