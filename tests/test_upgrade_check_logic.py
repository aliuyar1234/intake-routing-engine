from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ieim.store.upgrade import check_upgrade


class TestUpgradeCheckLogic(unittest.TestCase):
    def test_fails_closed_when_repo_has_no_migrations(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            repo_root = Path(td)
            (repo_root / "ieim" / "store" / "migrations").mkdir(parents=True, exist_ok=True)
            result = check_upgrade(repo_root=repo_root, pg_dsn=None)
            self.assertFalse(result.ok)
            self.assertEqual(result.status, "REPO_MIGRATIONS_MISSING")


if __name__ == "__main__":
    unittest.main()

