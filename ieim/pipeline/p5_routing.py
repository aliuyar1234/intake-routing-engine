from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

from ieim.audit.file_audit_log import ArtifactRef, FileAuditLogger, build_audit_event
from ieim.config import IEIMConfig, load_config
from ieim.identity.config_select import select_config_path_for_message
from ieim.observability.file_observability_log import FileObservabilityLogger, build_observability_event
from ieim.raw_store import sha256_prefixed
from ieim.route.evaluator import evaluate_routing


def _parse_rfc3339(dt: str) -> datetime:
    if dt.endswith("Z"):
        dt = dt[:-1] + "+00:00"
    return datetime.fromisoformat(dt)


@dataclass
class RoutingRunner:
    repo_root: Path
    normalized_dir: Path
    identity_dir: Path
    classification_dir: Path
    routing_out_dir: Path
    audit_logger: Optional[FileAuditLogger] = None
    obs_logger: Optional[FileObservabilityLogger] = None
    config_path_override: Optional[Path] = None

    def _load_config(self, *, nm: dict) -> IEIMConfig:
        config_path = self.config_path_override or select_config_path_for_message(
            repo_root=self.repo_root, normalized_message=nm
        )
        return load_config(path=config_path)

    def run(self) -> list[dict]:
        produced: list[dict] = []
        self.routing_out_dir.mkdir(parents=True, exist_ok=True)

        for nm_path in sorted(self.normalized_dir.glob("*.json")):
            nm_bytes = nm_path.read_bytes()
            nm = json.loads(nm_bytes.decode("utf-8"))

            message_id = str(nm["message_id"])
            run_id = str(nm["run_id"])

            cfg = self._load_config(nm=nm)

            identity_path = self.identity_dir / f"{message_id}.identity.json"
            classification_path = self.classification_dir / f"{message_id}.classification.json"

            identity_bytes = identity_path.read_bytes()
            classification_bytes = classification_path.read_bytes()

            identity = json.loads(identity_bytes.decode("utf-8"))
            classification = json.loads(classification_bytes.decode("utf-8"))

            t0 = time.perf_counter()
            result = evaluate_routing(
                repo_root=self.repo_root,
                config=cfg,
                normalized_message=nm,
                identity_result=identity,
                classification_result=classification,
            )
            dur_ms = int((time.perf_counter() - t0) * 1000)

            out_path = self.routing_out_dir / f"{message_id}.routing.json"
            out_bytes = (
                json.dumps(result.decision, indent=2, ensure_ascii=False, sort_keys=True).encode("utf-8")
                + b"\n"
            )
            tmp = out_path.with_suffix(out_path.suffix + ".tmp")
            tmp.write_bytes(out_bytes)
            tmp.replace(out_path)

            if self.obs_logger is not None:
                created_at_dt = _parse_rfc3339(str(nm["ingested_at"]))
                self.obs_logger.append(
                    build_observability_event(
                        event_type="STAGE_COMPLETE",
                        stage="ROUTE",
                        message_id=message_id,
                        run_id=run_id,
                        occurred_at=created_at_dt,
                        duration_ms=dur_ms,
                        status="OK",
                        fields={"queue_id": str(result.decision.get("queue_id") or "")},
                    )
                )

            if self.audit_logger is not None:
                created_at_dt = _parse_rfc3339(str(nm["ingested_at"]))
                input_ref = ArtifactRef(
                    schema_id=str(classification["schema_id"]),
                    uri=classification_path.name,
                    sha256=sha256_prefixed(classification_bytes),
                )
                output_ref = ArtifactRef(
                    schema_id=str(result.decision["schema_id"]),
                    uri=out_path.name,
                    sha256=sha256_prefixed(out_bytes),
                )
                event = build_audit_event(
                    message_id=message_id,
                    run_id=run_id,
                    stage="ROUTE",
                    actor_type="SYSTEM",
                    created_at=created_at_dt,
                    input_ref=input_ref,
                    output_ref=output_ref,
                    decision_hash=str(result.decision["decision_hash"]),
                    config_ref={"config_path": cfg.config_path, "config_sha256": cfg.config_sha256},
                    rules_ref=result.rules_ref,
                    model_info=None,
                    evidence=[],
                )
                self.audit_logger.append(event)

            produced.append(result.decision)

        return produced
