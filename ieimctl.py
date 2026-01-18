#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from ieim.audit.file_audit_log import FileAuditLogger
from ieim.audit.verify import verify_audit_logs
from ieim.config import load_config
from ieim.hitl.review_store import FileReviewStore
from ieim.hitl.service import HitlService
from ieim.identity.config_select import select_config_path_for_message
from ieim.ops.load_test import run_load_test
from ieim.ops.retention import load_retention_config, run_raw_retention
from ieim.pipeline.p6_reprocess import ReprocessRunner
from ieim.route.evaluator import evaluate_routing
from ieim.route.ruleset import load_routing_ruleset


def _require_dict(obj: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"{path} must be an object")
    return obj


def _require_list(obj: Any, *, path: str) -> list[Any]:
    if not isinstance(obj, list):
        raise ValueError(f"{path} must be a list")
    return list(obj)


def _lint_condition(cond: dict[str, Any], *, path: str) -> list[str]:
    errors: list[str] = []
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
        errors.append(f"{path}: unsupported keys: {sorted(unknown)}")

    for k in ("any", "all"):
        if k in cond:
            try:
                branches = _require_list(cond[k], path=f"{path}.{k}")
            except Exception as e:
                errors.append(f"{path}.{k}: {e}")
                continue
            for idx, branch in enumerate(branches):
                try:
                    branch_obj = _require_dict(branch, path=f"{path}.{k}[{idx}]")
                except Exception as e:
                    errors.append(f"{path}.{k}[{idx}]: {e}")
                    continue
                errors.extend(_lint_condition(branch_obj, path=f"{path}.{k}[{idx}]"))
    return errors


def cmd_rules_lint(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent
    ruleset = load_routing_ruleset(repo_root=repo_root, ruleset_path=args.ruleset_path)

    errors: list[str] = []

    seen_rule_ids: set[str] = set()
    for idx, rule in enumerate(ruleset.rules):
        rule_id = rule.get("rule_id")
        if not isinstance(rule_id, str) or not rule_id:
            errors.append(f"rules[{idx}].rule_id: missing")
        elif rule_id in seen_rule_ids:
            errors.append(f"rules[{idx}].rule_id: duplicate {rule_id}")
        else:
            seen_rule_ids.add(rule_id)

        prio = rule.get("priority")
        if not isinstance(prio, int):
            errors.append(f"rules[{idx}].priority: must be integer")

        when = rule.get("when")
        if not isinstance(when, dict):
            errors.append(f"rules[{idx}].when: must be object")
        else:
            errors.extend(_lint_condition(when, path=f"rules[{idx}].when"))

        then = rule.get("then")
        if not isinstance(then, dict):
            errors.append(f"rules[{idx}].then: must be object")
        else:
            for field in ("queue_id", "sla_id", "priority", "actions", "fail_closed"):
                if field not in then:
                    errors.append(f"rules[{idx}].then.{field}: missing")

    fallback = ruleset.fallback
    if "queue_id" not in fallback or "sla_id" not in fallback or "priority" not in fallback:
        errors.append("fallback: missing queue_id/sla_id/priority")

    if errors:
        print("RULES_LINT_FAILED")
        for e in errors[:200]:
            print(e)
        return 1

    print("RULES_LINT_OK")
    return 0


def cmd_rules_simulate(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent
    nm_dir = repo_root / args.normalized_dir
    gold_dir = repo_root / args.gold_dir

    failures = 0
    total = 0

    for nm_path in sorted(nm_dir.glob("*.json")):
        total += 1
        nm = json.loads(nm_path.read_text(encoding="utf-8"))
        msg_id = str(nm.get("message_id") or nm_path.stem)

        cfg = load_config(
            path=select_config_path_for_message(repo_root=repo_root, normalized_message=nm)
        )

        identity = json.loads((gold_dir / f"{msg_id}.identity.json").read_text(encoding="utf-8"))
        cls = json.loads((gold_dir / f"{msg_id}.classification.json").read_text(encoding="utf-8"))
        expected = json.loads((gold_dir / f"{msg_id}.routing.json").read_text(encoding="utf-8"))

        actual = evaluate_routing(
            repo_root=repo_root,
            config=cfg,
            normalized_message=nm,
            identity_result=identity,
            classification_result=cls,
        ).decision

        if actual != expected:
            failures += 1
            print(f"SIM_MISMATCH: {msg_id}")
            if failures >= 20:
                break

    if failures:
        print(f"RULES_SIMULATE_FAILED: {failures}/{total}")
        return 1

    print(f"RULES_SIMULATE_OK: {total}")
    return 0


def _resolve_repo_path(repo_root: Path, path: str) -> Path:
    p = Path(path)
    return p if p.is_absolute() else (repo_root / p)


def _run_python_script(*, repo_root: Path, script_rel: str) -> int:
    script = repo_root / script_rel
    if not script.exists():
        print(f"PACK_VERIFY_FAILED: missing {script_rel}")
        return 60

    try:
        cp = subprocess.run([sys.executable, str(script)], cwd=str(repo_root), check=False)
    except Exception as e:
        print(f"PACK_VERIFY_FAILED: failed to run {script_rel}: {e}")
        return 40

    return int(cp.returncode)


def cmd_audit_verify(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent
    audit_dir = _resolve_repo_path(repo_root, args.audit_dir)
    schema_path = repo_root / "schemas" / "audit_event.schema.json"

    if not audit_dir.exists():
        print(f"AUDIT_VERIFY_FAILED: missing audit dir: {audit_dir}")
        return 10

    result = verify_audit_logs(audit_dir=audit_dir, schema_path=schema_path)
    if result.files_checked == 0:
        print(f"AUDIT_VERIFY_FAILED: no audit logs found in: {audit_dir}")
        return 10

    if not result.ok:
        print("AUDIT_VERIFY_FAILED")
        for err in result.errors[:200]:
            print(err)
        return 60

    print(f"AUDIT_VERIFY_OK: files={result.files_checked} events={result.events_checked}")
    return 0


def _load_crm_mapping(path: Path) -> dict[str, list[str]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(obj, dict):
        raise ValueError("CRM mapping must be a JSON object")
    out: dict[str, list[str]] = {}
    for k, v in obj.items():
        if not isinstance(k, str) or not k:
            raise ValueError("CRM mapping keys must be non-empty strings")
        if not isinstance(v, list) or not all(isinstance(it, str) for it in v):
            raise ValueError(f"CRM mapping values must be list[str] for key: {k}")
        out[k] = list(v)
    return out


def cmd_reprocess(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent

    crm_mapping: dict[str, list[str]] = {}
    if args.crm_mapping is not None:
        crm_path = _resolve_repo_path(repo_root, args.crm_mapping)
        crm_mapping = _load_crm_mapping(crm_path)

    history_dir = None
    if args.history_dir is not None:
        history_dir = _resolve_repo_path(repo_root, args.history_dir)

    runner = ReprocessRunner(
        repo_root=repo_root,
        normalized_dir=_resolve_repo_path(repo_root, args.normalized_dir),
        attachments_dir=_resolve_repo_path(repo_root, args.attachments_dir),
        out_dir=_resolve_repo_path(repo_root, args.out_dir),
        message_id=args.message_id,
        crm_mapping=crm_mapping,
        history_dir=history_dir,
    )

    report = runner.run()
    status = str(report.get("status") or "")
    print(f"REPROCESS_STATUS: {status}")
    if status == "OK":
        return 0
    if status == "REVIEW_REQUIRED":
        return 30
    return 60


def cmd_pack_verify(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent

    scripts = [
        "scripts/check_placeholders.py",
        "scripts/check_single_definition_rule.py",
        "scripts/validate_schemas.py",
        "scripts/check_label_consistency.py",
        "scripts/check_manifest_completeness.py",
    ]
    for script in scripts:
        rc = _run_python_script(repo_root=repo_root, script_rel=script)
        if rc != 0:
            print(f"PACK_VERIFY_FAILED: {script}: rc={rc}")
            return int(rc)

    print("PACK_VERIFY_OK")
    return 0


def _load_corrections(path: Path) -> list[dict[str, Any]]:
    obj = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(obj, dict) and "corrections" in obj:
        obj = obj["corrections"]
    if not isinstance(obj, list) or not all(isinstance(it, dict) for it in obj):
        raise ValueError("corrections JSON must be a list[object] or {corrections: list[object]}")
    return [dict(it) for it in obj]


def cmd_hitl_list(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent
    hitl_dir = _resolve_repo_path(repo_root, args.hitl_dir)

    items = FileReviewStore(base_dir=hitl_dir).list_queue(queue_id=args.queue_id)
    for it in items:
        rid = str(it.get("review_item_id") or "")
        mid = str(it.get("message_id") or "")
        status = str(it.get("status") or "")
        print(f"{rid} {mid} {status}")
    print(f"HITL_LIST_OK: {len(items)}")
    return 0


def cmd_hitl_submit_correction(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent
    hitl_dir = _resolve_repo_path(repo_root, args.hitl_dir)

    store = FileReviewStore(base_dir=hitl_dir)
    review_path = store.find_path(review_item_id=args.review_item_id)
    if review_path is None:
        print(f"HITL_SUBMIT_FAILED: review item not found: {args.review_item_id}")
        return 10

    try:
        corrections = _load_corrections(_resolve_repo_path(repo_root, args.corrections_json))
    except Exception as e:
        print(f"HITL_SUBMIT_FAILED: invalid corrections JSON: {e}")
        return 10

    audit_logger = None
    if args.audit_base_dir is not None:
        audit_logger = FileAuditLogger(base_dir=_resolve_repo_path(repo_root, args.audit_base_dir))

    service = HitlService(repo_root=repo_root, hitl_dir=hitl_dir, audit_logger=audit_logger)
    out = service.submit_correction(
        review_item_path=review_path,
        actor_id=args.actor_id,
        corrections=corrections,
        note=args.note,
    )
    print(f"HITL_SUBMIT_OK: {out.as_posix()}")
    return 0


def _parse_rfc3339(dt: str) -> datetime:
    if dt.endswith("Z"):
        dt = dt[:-1] + "+00:00"
    return datetime.fromisoformat(dt)


def cmd_retention_run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent
    base_dir = _resolve_repo_path(repo_root, args.base_dir)
    normalized_dir = _resolve_repo_path(repo_root, args.normalized_dir)
    attachments_dir = _resolve_repo_path(repo_root, args.attachments_dir)

    derived_base_dir = None
    if args.derived_base_dir is not None:
        derived_base_dir = _resolve_repo_path(repo_root, args.derived_base_dir)

    now = datetime.now(timezone.utc).replace(microsecond=0)
    if args.now is not None:
        try:
            now = _parse_rfc3339(args.now)
        except Exception as e:
            print(f"RETENTION_RUN_FAILED: invalid --now: {e}")
            return 10

    try:
        retention = load_retention_config(path=_resolve_repo_path(repo_root, args.config))
    except RuntimeError as e:
        print(f"RETENTION_RUN_FAILED: {e}")
        return 40
    except Exception as e:
        print(f"RETENTION_RUN_FAILED: invalid config: {e}")
        return 10

    report_path = None
    if args.report_path is not None:
        report_path = _resolve_repo_path(repo_root, args.report_path)

    try:
        report = run_raw_retention(
            base_dir=base_dir,
            derived_base_dir=derived_base_dir,
            normalized_dir=normalized_dir,
            attachments_dir=attachments_dir,
            raw_days=retention.raw_days,
            now=now,
            dry_run=not args.apply,
            report_path=report_path,
        )
    except Exception as e:
        print(f"RETENTION_RUN_FAILED: {e}")
        return 60

    if report_path is not None:
        print(f"RETENTION_RUN_OK: {report_path.as_posix()}")
    else:
        print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
        print("RETENTION_RUN_OK")
    return 0


def cmd_loadtest_run(args: argparse.Namespace) -> int:
    repo_root = Path(__file__).resolve().parent

    crm_mapping: dict[str, list[str]] = {}
    if args.crm_mapping is not None:
        try:
            crm_mapping = _load_crm_mapping(_resolve_repo_path(repo_root, args.crm_mapping))
        except Exception as e:
            print(f"LOADTEST_FAILED: invalid --crm-mapping: {e}")
            return 10

    cfg_path = None
    if args.config is not None:
        cfg_path = _resolve_repo_path(repo_root, args.config)

    try:
        report = run_load_test(
            repo_root=repo_root,
            normalized_dir=_resolve_repo_path(repo_root, args.normalized_dir),
            attachments_dir=_resolve_repo_path(repo_root, args.attachments_dir),
            iterations=int(args.iterations),
            config_path=cfg_path,
            crm_mapping=crm_mapping,
        )
    except Exception as e:
        print(f"LOADTEST_FAILED: {e}")
        return 60

    if args.report_path is not None:
        out_path = _resolve_repo_path(repo_root, args.report_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_text(
            json.dumps(report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n",
            encoding="utf-8",
        )
        print(f"LOADTEST_OK: {out_path.as_posix()}")
        return 0

    print(json.dumps(report.to_dict(), ensure_ascii=False, sort_keys=True))
    print("LOADTEST_OK")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ieimctl")
    sub = parser.add_subparsers(dest="command", required=True)

    pack = sub.add_parser("pack")
    pack_sub = pack.add_subparsers(dest="pack_command", required=True)

    pack_verify = pack_sub.add_parser("verify")
    pack_verify.set_defaults(func=cmd_pack_verify)

    rules = sub.add_parser("rules")
    rules_sub = rules.add_subparsers(dest="rules_command", required=True)

    lint = rules_sub.add_parser("lint")
    lint.add_argument(
        "--ruleset-path",
        default="configs/routing_tables/routing_rules_v1.4.1.json",
        help="Path to routing ruleset JSON (repo-relative).",
    )
    lint.set_defaults(func=cmd_rules_lint)

    sim = rules_sub.add_parser("simulate")
    sim.add_argument("--normalized-dir", default="data/samples/emails")
    sim.add_argument("--gold-dir", default="data/samples/gold")
    sim.set_defaults(func=cmd_rules_simulate)

    audit = sub.add_parser("audit")
    audit_sub = audit.add_subparsers(dest="audit_command", required=True)

    verify = audit_sub.add_parser("verify")
    verify.add_argument(
        "--audit-dir",
        default="audit",
        help="Audit directory (repo-relative unless absolute).",
    )
    verify.set_defaults(func=cmd_audit_verify)

    reprocess = sub.add_parser("reprocess")
    reprocess.add_argument("--message-id", required=True)
    reprocess.add_argument("--normalized-dir", default="data/samples/emails")
    reprocess.add_argument("--attachments-dir", default="data/samples/attachments")
    reprocess.add_argument("--out-dir", required=True)
    reprocess.add_argument(
        "--history-dir",
        default=None,
        help="Optional directory with historical outputs (e.g., data/samples/gold).",
    )
    reprocess.add_argument(
        "--crm-mapping",
        default=None,
        help="Optional JSON file mapping sender email to policy numbers.",
    )
    reprocess.set_defaults(func=cmd_reprocess)

    hitl = sub.add_parser("hitl")
    hitl_sub = hitl.add_subparsers(dest="hitl_command", required=True)

    hitl_list = hitl_sub.add_parser("list")
    hitl_list.add_argument("--hitl-dir", default="hitl", help="HITL base directory.")
    hitl_list.add_argument("--queue-id", required=True, help="Queue id to list (canonical).")
    hitl_list.set_defaults(func=cmd_hitl_list)

    hitl_submit = hitl_sub.add_parser("submit-correction")
    hitl_submit.add_argument("--hitl-dir", default="hitl", help="HITL base directory.")
    hitl_submit.add_argument("--review-item-id", required=True, help="Review item id.")
    hitl_submit.add_argument("--actor-id", required=True, help="Reviewer identifier.")
    hitl_submit.add_argument("--corrections-json", required=True, help="Path to corrections JSON file.")
    hitl_submit.add_argument("--note", default=None, help="Optional free-text note.")
    hitl_submit.add_argument(
        "--audit-base-dir",
        default=None,
        help="Optional base directory to append audit events (creates <base>/audit).",
    )
    hitl_submit.set_defaults(func=cmd_hitl_submit_correction)

    retention = sub.add_parser("retention")
    retention_sub = retention.add_subparsers(dest="retention_command", required=True)

    retention_run = retention_sub.add_parser("run")
    retention_run.add_argument("--config", default="configs/prod.yaml", help="Config file (repo-relative).")
    retention_run.add_argument("--base-dir", required=True, help="Base dir containing raw_store/ for deletion.")
    retention_run.add_argument(
        "--derived-base-dir",
        default=None,
        help="Optional base dir for derived_store (defaults to --base-dir).",
    )
    retention_run.add_argument(
        "--normalized-dir",
        required=True,
        help="Directory with NormalizedMessage JSON files (repo-relative unless absolute).",
    )
    retention_run.add_argument(
        "--attachments-dir",
        required=True,
        help="Directory with AttachmentArtifact JSON files (repo-relative unless absolute).",
    )
    retention_run.add_argument(
        "--apply",
        action="store_true",
        help="Apply deletions (default is dry-run).",
    )
    retention_run.add_argument(
        "--now",
        default=None,
        help="Optional RFC3339 timestamp to use as 'now' (e.g., 2026-01-18T00:00:00Z).",
    )
    retention_run.add_argument(
        "--report-path",
        default=None,
        help="Optional path to write a JSON report (repo-relative unless absolute).",
    )
    retention_run.set_defaults(func=cmd_retention_run)

    loadtest = sub.add_parser("loadtest")
    loadtest_sub = loadtest.add_subparsers(dest="loadtest_command", required=True)

    loadtest_run = loadtest_sub.add_parser("run")
    loadtest_run.add_argument("--normalized-dir", default="data/samples/emails")
    loadtest_run.add_argument("--attachments-dir", default="data/samples/attachments")
    loadtest_run.add_argument("--iterations", default=1, type=int)
    loadtest_run.add_argument(
        "--config",
        default=None,
        help="Optional config file to apply to all messages (repo-relative unless absolute).",
    )
    loadtest_run.add_argument(
        "--crm-mapping",
        default=None,
        help="Optional JSON file mapping sender email to policy numbers.",
    )
    loadtest_run.add_argument(
        "--report-path",
        default=None,
        help="Optional path to write a JSON report (repo-relative unless absolute).",
    )
    loadtest_run.set_defaults(func=cmd_loadtest_run)

    args = parser.parse_args(argv)
    return int(args.func(args))


if __name__ == "__main__":
    raise SystemExit(main())
