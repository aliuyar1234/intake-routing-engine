import unittest

import ieimctl


class TestLoadtestCliProfiles(unittest.TestCase):
    def test_enterprise_smoke_profile_runs(self) -> None:
        rc = ieimctl.main(["loadtest", "run", "--profile", "enterprise_smoke", "--config", "configs/dev.yaml"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()

