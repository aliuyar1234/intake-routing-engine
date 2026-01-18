from __future__ import annotations

import json
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any

from ieim.config import IEIMConfig
from ieim.determinism.decision_hash import decision_hash
from ieim.route.ruleset import RoutingRuleset, load_routing_ruleset


@lru_cache(maxsize=1)
def _routing_schema_id_and_version() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas" / "routing_decision.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str) or not schema_id:
        raise ValueError("routing_decision.schema.json missing $id")
    version = schema_id.rsplit(":", 1)[-1]
    return schema_id, version


@dataclass(frozen=True)
class RoutingContext:
    identity_status: str
    primary_intent: str
    product_line: str
    urgency: str
    risk_flags: frozenset[str]


def _require_list_of_str(value: Any, *, path: str) -> list[str]:
    if not isinstance(value, list) or not all(isinstance(x, str) and x for x in value):
        raise ValueError(f"{path} must be a list of non-empty strings")
    return list(value)


def _match_condition(cond: dict[str, Any], ctx: RoutingContext) -> bool:
    supported_keys = {
        "risk_flags_any",
        "risk_flags_not_any",
        "primary_intent_in",
        "primary_intent_not_in",
        "identity_status_in",
        "product_line_in",
        "any",
        "all",
    }
    unknown = set(cond.keys()) - supported_keys
    if unknown:
        raise ValueError(f"unsupported condition keys: {sorted(unknown)}")

    if "risk_flags_any" in cond:
        values = _require_list_of_str(cond["risk_flags_any"], path="when.risk_flags_any")
        if not any(v in ctx.risk_flags for v in values):
            return False

    if "risk_flags_not_any" in cond:
        values = _require_list_of_str(cond["risk_flags_not_any"], path="when.risk_flags_not_any")
        if any(v in ctx.risk_flags for v in values):
            return False

    if "primary_intent_in" in cond:
        values = _require_list_of_str(cond["primary_intent_in"], path="when.primary_intent_in")
        if ctx.primary_intent not in values:
            return False

    if "primary_intent_not_in" in cond:
        values = _require_list_of_str(cond["primary_intent_not_in"], path="when.primary_intent_not_in")
        if ctx.primary_intent in values:
            return False

    if "identity_status_in" in cond:
        values = _require_list_of_str(cond["identity_status_in"], path="when.identity_status_in")
        if ctx.identity_status not in values:
            return False

    if "product_line_in" in cond:
        values = _require_list_of_str(cond["product_line_in"], path="when.product_line_in")
        if ctx.product_line not in values:
            return False

    if "any" in cond:
        branches = cond["any"]
        if not isinstance(branches, list) or not all(isinstance(x, dict) for x in branches):
            raise ValueError("when.any must be a list of objects")
        if not any(_match_condition(x, ctx) for x in branches):
            return False

    if "all" in cond:
        branches = cond["all"]
        if not isinstance(branches, list) or not all(isinstance(x, dict) for x in branches):
            raise ValueError("when.all must be a list of objects")
        if not all(_match_condition(x, ctx) for x in branches):
            return False

    return True


def _sorted_rules(ruleset: RoutingRuleset) -> list[dict[str, Any]]:
    def prio(rule: dict[str, Any]) -> int:
        v = rule.get("priority")
        if not isinstance(v, int):
            raise ValueError("rule priority must be integer")
        return v

    return sorted(ruleset.rules, key=prio, reverse=True)


@dataclass(frozen=True)
class RoutingResult:
    decision: dict[str, Any]
    rules_ref: dict[str, Any]


def evaluate_routing(
    *,
    repo_root: Path,
    config: IEIMConfig,
    normalized_message: dict,
    identity_result: dict,
    classification_result: dict,
) -> RoutingResult:
    schema_id, schema_version = _routing_schema_id_and_version()

    ruleset = load_routing_ruleset(repo_root=repo_root, ruleset_path=config.routing.ruleset_path)

    ctx = RoutingContext(
        identity_status=str(identity_result.get("status") or ""),
        primary_intent=str((classification_result.get("primary_intent") or {}).get("label") or ""),
        product_line=str((classification_result.get("product_line") or {}).get("label") or ""),
        urgency=str((classification_result.get("urgency") or {}).get("label") or ""),
        risk_flags=frozenset(
            str(r.get("label") or "") for r in (classification_result.get("risk_flags") or [])
        ),
    )

    matched: dict[str, Any] | None = None
    for rule in _sorted_rules(ruleset):
        when = rule.get("when") or {}
        if not isinstance(when, dict):
            raise ValueError("rule.when must be an object")
        if _match_condition(when, ctx):
            matched = rule
            break

    then: dict[str, Any]
    rule_id: str
    if matched is None:
        then = ruleset.fallback
        rule_id = "ROUTE_FALLBACK"
    else:
        then_obj = matched.get("then")
        if not isinstance(then_obj, dict):
            raise ValueError("rule.then must be an object")
        then = then_obj
        rule_id = str(matched.get("rule_id") or "")
        if not rule_id:
            raise ValueError("rule missing rule_id")

    # Incident toggle: force all messages into a review queue (fail-closed).
    if bool(config.incident.force_review):
        then = dict(ruleset.fallback)
        then["queue_id"] = str(config.incident.force_review_queue_id)
        then["fail_closed"] = True
        then["fail_closed_reason"] = "INCIDENT_FORCE_REVIEW"
        then["actions"] = ["ATTACH_ORIGINAL_EMAIL"]
        rule_id = "INCIDENT_FORCE_REVIEW"

    decision = {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "message_id": str(normalized_message["message_id"]),
        "run_id": str(normalized_message["run_id"]),
        "queue_id": str(then.get("queue_id") or ""),
        "sla_id": str(then.get("sla_id") or ""),
        "priority": int(then.get("priority") or 0),
        "actions": list(then.get("actions") or []),
        "rule_id": rule_id,
        "rule_version": ruleset.ruleset_version,
        "fail_closed": bool(then.get("fail_closed")),
        "fail_closed_reason": then.get("fail_closed_reason"),
        "created_at": str(normalized_message["ingested_at"]),
        "decision_hash": "sha256:" + ("0" * 64),
    }

    # Incident toggle: block case creation for configured risk flags.
    block_flags = set(str(x) for x in (config.incident.block_case_create_risk_flags_any or ()))
    if block_flags and any(f in ctx.risk_flags for f in block_flags):
        actions = [str(a) for a in (decision.get("actions") or []) if isinstance(a, str)]
        actions = [a for a in actions if a != "CREATE_CASE"]
        if "BLOCK_CASE_CREATE" not in actions:
            actions.insert(0, "BLOCK_CASE_CREATE")
        decision["actions"] = actions
        decision["fail_closed"] = True
        if not decision.get("fail_closed_reason"):
            decision["fail_closed_reason"] = "INCIDENT_BLOCK_CASE_CREATE"

    rules_ref = {
        "ruleset_path": ruleset.ruleset_path,
        "ruleset_sha256": ruleset.ruleset_sha256,
        "ruleset_version": ruleset.ruleset_version,
    }

    decision_input = {
        "system_id": config.system_id,
        "canonical_spec_semver": config.canonical_spec_semver,
        "stage": "ROUTE",
        "message_fingerprint": str(normalized_message.get("message_fingerprint") or ""),
        "raw_mime_sha256": str(normalized_message.get("raw_mime_sha256") or ""),
        "config_ref": {"config_path": config.config_path, "config_sha256": config.config_sha256},
        "determinism_mode": config.determinism_mode,
        "rules_ref": rules_ref,
        "input": {
            "identity_status": ctx.identity_status,
            "primary_intent": ctx.primary_intent,
            "product_line": ctx.product_line,
            "urgency": ctx.urgency,
            "risk_flags": sorted(ctx.risk_flags),
        },
        "decision": {
            "queue_id": decision["queue_id"],
            "sla_id": decision["sla_id"],
            "priority": decision["priority"],
            "actions": list(decision["actions"]),
            "rule_id": decision["rule_id"],
            "fail_closed": decision["fail_closed"],
            "fail_closed_reason": decision.get("fail_closed_reason"),
        },
    }

    decision["decision_hash"] = decision_hash(decision_input)

    return RoutingResult(decision=decision, rules_ref=rules_ref)
