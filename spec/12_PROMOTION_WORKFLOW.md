# Promotion workflow (offline governance)

This document defines the offline, approval-gated promotion workflow for routing rulesets, model/prompt versions, and templates.

The design goal is to ensure production remains fail-closed and does not auto-learn. Promotions are explicit, versioned, and auditable.

## Promotion principles

- promotions are initiated by a change request (human initiated)
- promotions require approvals (roles depend on the change type)
- promotions require regression checks against the golden sample corpus
- promotions are reversible (rollback to the last promoted version is always possible)
- production never auto-applies reviewer feedback without an explicit promotion

## Change request record (conceptual)

Each promotion should be accompanied by a versioned change request record that includes:

- change_id (stable identifier)
- change_type (ruleset, model, prompt, template)
- proposed_version and current_version
- artifacts changed (paths + hashes)
- evidence of required checks (lint results, simulation results, test run identifiers)
- approvals (actor identifiers + timestamps)
- rollback plan

## Required checks

### Routing rulesets

Before promotion:

- rules lint must pass (`ieimctl rules lint`)
- rules simulation against the golden corpus must pass (`ieimctl rules simulate`)
- pack verification must pass (`bash scripts/verify_pack.sh`)

### Model/prompt versions

Before promotion:

- pinned model identifiers must be recorded
- prompts must be versioned and hashed
- offline evaluation must show no safety regression on the golden corpus
- pack verification must pass (`bash scripts/verify_pack.sh`)

### Templates

Before promotion:

- templates must pass policy checks (no prohibited content)
- pack verification must pass (`bash scripts/verify_pack.sh`)

## Approvals

Minimum approval requirements:

- routing ruleset: reviewer + administrator
- model/prompt: reviewer + administrator (and security officer if external LLM egress changes)
- privacy-related templates: privacy officer + administrator

Approvals must be recorded in the operational audit system as part of the promotion process.

## Rollback

Rollback requires:

- restoring the last promoted artifact versions
- re-running pack verification
- recording the rollback as an auditable event (with change_id linkage)

