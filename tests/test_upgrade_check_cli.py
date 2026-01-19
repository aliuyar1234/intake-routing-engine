import unittest

import ieimctl


class TestUpgradeCheckCli(unittest.TestCase):
    def test_upgrade_check_offline_ok(self) -> None:
        rc = ieimctl.main(["upgrade", "check", "--config", "configs/prod.yaml"])
        self.assertEqual(rc, 0)

    def test_upgrade_migrate_requires_dsn(self) -> None:
        rc = ieimctl.main(["upgrade", "migrate", "--config", "configs/prod.yaml"])
        self.assertEqual(rc, 10)


if __name__ == "__main__":
    unittest.main()

