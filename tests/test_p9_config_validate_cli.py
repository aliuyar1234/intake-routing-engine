import unittest

import ieimctl


class TestP9ConfigValidateCLI(unittest.TestCase):
    def test_config_validate_dev_and_prod(self) -> None:
        rc = ieimctl.main(["config", "validate", "--config", "configs/dev.yaml"])
        self.assertEqual(rc, 0)

        rc = ieimctl.main(["config", "validate", "--config", "configs/prod.yaml"])
        self.assertEqual(rc, 0)


if __name__ == "__main__":
    unittest.main()

