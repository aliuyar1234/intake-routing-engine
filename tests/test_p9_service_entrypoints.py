import subprocess
import sys
import unittest
from pathlib import Path


class TestP9ServiceEntrypoints(unittest.TestCase):
    def test_entrypoints_start_in_dry_run(self) -> None:
        root = Path(__file__).resolve().parents[1]
        for module in ("ieim.api.app", "ieim.worker.main", "ieim.scheduler.main"):
            cp = subprocess.run(
                [
                    sys.executable,
                    "-m",
                    module,
                    "--dry-run",
                    "--config",
                    "configs/dev.yaml",
                ],
                cwd=str(root),
                capture_output=True,
                text=True,
                check=False,
            )
            if cp.returncode != 0:
                msg = f"{module} failed: rc={cp.returncode}\nstdout:\n{cp.stdout}\nstderr:\n{cp.stderr}"
                raise AssertionError(msg)


if __name__ == "__main__":
    unittest.main()

