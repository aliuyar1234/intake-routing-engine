from __future__ import annotations

import os
import unittest
from pathlib import Path


class TestSbomPresence(unittest.TestCase):
    def test_release_artifacts_exist_in_release_mode(self) -> None:
        release_dir = os.getenv("IEIM_RELEASE_ARTIFACT_DIR")
        if not release_dir:
            self.skipTest("IEIM_RELEASE_ARTIFACT_DIR not set")

        base = Path(release_dir)
        self.assertTrue(base.is_dir(), f"missing release dir: {base}")

        required_files = [
            "ieim-api.spdx.json",
            "ieim-worker.spdx.json",
            "ieim-scheduler.spdx.json",
            "provenance.json",
            "provenance.sig",
            "provenance.crt",
            "SHA256SUMS.txt",
        ]
        for name in required_files:
            self.assertTrue((base / name).is_file(), f"missing release artifact: {name}")

        self.assertTrue(
            any(base.glob("ieim-*.tgz")),
            "missing Helm chart package (expected ieim-<version>.tgz)",
        )


if __name__ == "__main__":
    unittest.main()

