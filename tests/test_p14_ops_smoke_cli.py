import tempfile
import unittest
from pathlib import Path

import ieimctl


class TestP14OpsSmokeCli(unittest.TestCase):
    def test_ops_smoke_cli_runs(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        (repo_root / "out").mkdir(parents=True, exist_ok=True)
        with tempfile.TemporaryDirectory(dir=str(repo_root / "out")) as td:
            rc = ieimctl.main(
                [
                    "ops",
                    "smoke",
                    "--config",
                    "configs/dev.yaml",
                    "--out-dir",
                    td,
                    "--samples",
                    "data/samples",
                ]
            )
            self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()
