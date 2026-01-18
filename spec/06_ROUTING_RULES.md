# Routing rules

Routing is deterministic and uses a versioned decision table. Canonical queue IDs, SLA IDs, and risk overrides are defined in `spec/00_CANONICAL.md`.

The routing table file is located at the canonical path defined in `spec/00_CANONICAL.md`.

## Inputs

Routing consumes only validated, canonical inputs:
- identity status
- primary intent
- product line
- urgency
- risk flags
- (optional) validated high-impact entities

## Evaluation order

The engine evaluates rules in priority order and stops at the first matching rule. The rule order must ensure fail-closed safety:

1. Security overrides (malware)
2. Privacy/GDPR requests
3. Legal/regulatory overrides
4. Fraud overrides
5. Identity needs-review gating
6. Product/intent routing
7. Fallback (no rule match) to general review

## Identity fail-closed modifier

If identity status indicates ambiguity and no hard override applies, routing must select a review queue and add a request-info draft action when appropriate.

## Rule versioning and change management

- The routing ruleset has a semantic version.
- Any change requires:
  - lint check
  - simulation against the golden set in `data/samples/gold/`
  - approval
  - ability to roll back to the prior version

## Actions

Routing outputs a list of actions. The canonical action strings are defined in `spec/00_CANONICAL.md`.

## No-rule-match behavior

If no rule matches, routing must fail closed to the general review queue and record the reason.
