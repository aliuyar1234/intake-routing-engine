import json
import tempfile
import unittest
import uuid
from datetime import datetime, timezone
from pathlib import Path

import ieimctl

from ieim.audit.file_audit_log import ArtifactRef, FileAuditLogger, build_audit_event
from ieim.audit.verify import verify_audit_logs


class TestP6AuditVerifyAndReprocess(unittest.TestCase):
    def test_audit_verify_detects_tampering(self) -> None:
        root = Path(__file__).resolve().parents[1]
        schema_path = root / "schemas" / "audit_event.schema.json"

        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            message_id = "11111111-1111-1111-1111-111111111111"
            run_id = "22222222-2222-2222-2222-222222222222"

            logger = FileAuditLogger(base_dir=base)
            created_at = datetime(2026, 1, 17, 8, 0, 0, tzinfo=timezone.utc)

            input_ref = ArtifactRef(schema_id="IN", uri="in.json", sha256="sha256:" + ("0" * 64))
            out1 = ArtifactRef(schema_id="OUT", uri="o1.json", sha256="sha256:" + ("1" * 64))
            out2 = ArtifactRef(schema_id="OUT", uri="o2.json", sha256="sha256:" + ("2" * 64))

            ev1 = build_audit_event(
                message_id=message_id,
                run_id=run_id,
                stage="IDENTITY",
                actor_type="SYSTEM",
                created_at=created_at,
                input_ref=input_ref,
                output_ref=out1,
                decision_hash="sha256:" + ("a" * 64),
            )
            logger.append(ev1)

            ev2 = build_audit_event(
                message_id=message_id,
                run_id=run_id,
                stage="ROUTE",
                actor_type="SYSTEM",
                created_at=created_at,
                input_ref=input_ref,
                output_ref=out2,
                decision_hash="sha256:" + ("b" * 64),
            )
            logger.append(ev2)

            audit_dir = base / "audit"
            ok = verify_audit_logs(audit_dir=audit_dir, schema_path=schema_path)
            self.assertTrue(ok.ok)

            rc = ieimctl.main(["audit", "verify", "--audit-dir", str(audit_dir)])
            self.assertEqual(rc, 0)

            audit_path = audit_dir / message_id / f"{run_id}.jsonl"
            lines = [ln for ln in audit_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            self.assertEqual(len(lines), 2)
            second = json.loads(lines[1])
            second["stage"] = "TAMPERED"
            lines[1] = json.dumps(second, ensure_ascii=False)
            audit_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

            bad = verify_audit_logs(audit_dir=audit_dir, schema_path=schema_path)
            self.assertFalse(bad.ok)
            self.assertTrue(any("event_hash mismatch" in e for e in bad.errors))

            rc = ieimctl.main(["audit", "verify", "--audit-dir", str(audit_dir)])
            self.assertNotEqual(rc, 0)

    def test_reprocess_replays_decision_hashes_and_emits_signals(self) -> None:
        root = Path(__file__).resolve().parents[1]
        message_id = "a3e96afd-bd77-5b03-8cf0-64ac1ec17786"

        nm = json.loads((root / "data" / "samples" / "emails" / f"{message_id}.json").read_text(encoding="utf-8"))
        historical_run_id = str(nm["run_id"])
        reprocess_run_id = str(uuid.uuid5(uuid.NAMESPACE_URL, f"reprocess:{message_id}:{historical_run_id}"))

        with tempfile.TemporaryDirectory() as td:
            out_dir = Path(td)
            crm_path = out_dir / "crm_mapping.json"
            crm_path.write_text(
                json.dumps({"kunde1@example.test": ["45-1234567"]}, indent=2) + "\n",
                encoding="utf-8",
            )

            rc = ieimctl.main(
                [
                    "reprocess",
                    "--message-id",
                    message_id,
                    "--normalized-dir",
                    "data/samples/emails",
                    "--attachments-dir",
                    "data/samples/attachments",
                    "--history-dir",
                    "data/samples/gold",
                    "--config",
                    "configs/test_baseline.yaml",
                    "--crm-mapping",
                    str(crm_path),
                    "--out-dir",
                    str(out_dir),
                ]
            )
            self.assertEqual(rc, 0)

            run_dir = out_dir / "reprocess" / message_id / reprocess_run_id
            report_path = run_dir / "reprocess_report.json"
            self.assertTrue(report_path.exists())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(report["status"], "OK")

            audit_dir = run_dir / "audit"
            rc = ieimctl.main(["audit", "verify", "--audit-dir", str(audit_dir)])
            self.assertEqual(rc, 0)

            obs_path = run_dir / "observability" / message_id / f"{reprocess_run_id}.jsonl"
            self.assertTrue(obs_path.exists())
            obs_lines = [ln for ln in obs_path.read_text(encoding="utf-8").splitlines() if ln.strip()]
            stages = {json.loads(ln).get("stage") for ln in obs_lines}
            self.assertTrue({"IDENTITY", "CLASSIFY", "EXTRACT", "ROUTE", "REPROCESS"}.issubset(stages))


if __name__ == "__main__":
    unittest.main()
