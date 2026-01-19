import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

from ieim.audit.verify import verify_audit_logs


def _bash_available() -> bool:
    try:
        cp = subprocess.run(
            ["bash", "--version"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
    except FileNotFoundError:
        return False
    return cp.returncode == 0


@unittest.skipUnless(_bash_available(), "bash not available")
class TestBackupRestoreSmoke(unittest.TestCase):
    def test_backup_and_restore_filesystem_runtime(self) -> None:
        root = Path(__file__).resolve().parents[1]
        backup_script = "infra/backup/backup.sh"
        restore_script = "infra/backup/restore.sh"

        (root / "out").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(root / "out")) as td:
            td_path = Path(td)
            ingest_out = td_path / "runtime"
            backup_dir = td_path / "backup"
            restore_root = td_path / "restore"
            restored_cfg = restore_root / "runtime.yaml"
            restored_runtime = restore_root / "runtime"

            ingest = subprocess.run(
                [
                    sys.executable,
                    "ieimctl.py",
                    "ingest",
                    "simulate",
                    "--adapter",
                    "filesystem",
                    "--samples",
                    "data/samples",
                    "--out-dir",
                    str(ingest_out),
                    "--limit",
                    "500",
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if ingest.returncode != 0:
                raise AssertionError(f"ingest simulate failed\n{ingest.stdout}\n{ingest.stderr}")

            ingest_out_rel = ingest_out.relative_to(root).as_posix()
            backup_dir_rel = backup_dir.relative_to(root).as_posix()
            restored_cfg_rel = restored_cfg.relative_to(root).as_posix()
            restored_runtime_rel = restored_runtime.relative_to(root).as_posix()

            backup = subprocess.run(
                [
                    "bash",
                    backup_script,
                    "--out",
                    backup_dir_rel,
                    "--config",
                    "configs/dev.yaml",
                    "--runtime-dir",
                    ingest_out_rel,
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if backup.returncode != 0:
                raise AssertionError(f"backup.sh failed\n{backup.stdout}\n{backup.stderr}")

            restore = subprocess.run(
                [
                    "bash",
                    restore_script,
                    "--in",
                    backup_dir_rel,
                    "--runtime-dir",
                    restored_runtime_rel,
                    "--config-dest",
                    restored_cfg_rel,
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                check=False,
            )
            if restore.returncode != 0:
                raise AssertionError(f"restore.sh failed\n{restore.stdout}\n{restore.stderr}")

            self.assertTrue(restored_cfg.exists())

            schema_path = root / "schemas" / "audit_event.schema.json"
            audit_result = verify_audit_logs(audit_dir=restored_runtime / "audit", schema_path=schema_path)
            self.assertTrue(audit_result.ok)
            self.assertGreater(audit_result.files_checked, 0)


if __name__ == "__main__":
    unittest.main()
