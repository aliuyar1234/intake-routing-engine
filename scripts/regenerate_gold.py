#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from ieim.identity.adapters import InMemoryCRMAdapter, InMemoryClaimsAdapter, InMemoryPolicyAdapter
from ieim.pipeline.p3_identity_resolution import IdentityResolutionRunner
from ieim.pipeline.p4_classify_extract import ClassifyExtractRunner
from ieim.pipeline.p5_routing import RoutingRunner


def _write_json(path: Path, obj: dict) -> None:
    path.write_text(
        json.dumps(obj, indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8"
    )


def main() -> int:
    repo_root = REPO_ROOT

    normalized_dir = repo_root / "data" / "samples" / "emails"
    attachments_dir = repo_root / "data" / "samples" / "attachments"
    gold_dir = repo_root / "data" / "samples" / "gold"
    gold_dir.mkdir(parents=True, exist_ok=True)

    # P3 gold (identity)
    crm = InMemoryCRMAdapter({"kunde1@example.test": ["45-1234567"]})
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        identity_runner = IdentityResolutionRunner(
            repo_root=repo_root,
            normalized_dir=normalized_dir,
            attachments_dir=attachments_dir,
            identity_out_dir=base / "identity",
            drafts_out_dir=base / "drafts",
            policy_adapter=InMemoryPolicyAdapter(),
            claims_adapter=InMemoryClaimsAdapter(),
            crm_adapter=crm,
            audit_logger=None,
            obs_logger=None,
        )
        identity_results = identity_runner.run()
        for res in identity_results:
            _write_json(gold_dir / f"{res['message_id']}.identity.json", res)

    # P4 gold (classification + extraction)
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        cls_runner = ClassifyExtractRunner(
            repo_root=repo_root,
            normalized_dir=normalized_dir,
            attachments_dir=attachments_dir,
            classification_out_dir=base / "classification",
            extraction_out_dir=base / "extraction",
            audit_logger=None,
            obs_logger=None,
        )
        produced = cls_runner.run()
        for cls, ex in produced:
            _write_json(gold_dir / f"{cls['message_id']}.classification.json", cls)
            _write_json(gold_dir / f"{ex['message_id']}.extraction.json", ex)

    # P5 gold (routing)
    with tempfile.TemporaryDirectory() as td:
        base = Path(td)
        routing_runner = RoutingRunner(
            repo_root=repo_root,
            normalized_dir=normalized_dir,
            identity_dir=gold_dir,
            classification_dir=gold_dir,
            routing_out_dir=base / "routing",
            audit_logger=None,
            obs_logger=None,
        )
        routing_results = routing_runner.run()
        for decision in routing_results:
            _write_json(gold_dir / f"{decision['message_id']}.routing.json", decision)

    print("REGENERATE_GOLD_OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
