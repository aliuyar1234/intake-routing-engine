from __future__ import annotations

import re
import unittest
from pathlib import Path

import yaml


class TestVersionConsistency(unittest.TestCase):
    def test_version_matches_spec_configs_and_chart(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        version = (repo_root / "VERSION").read_text(encoding="utf-8").strip()
        semver_re = re.compile(
            r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
        )
        self.assertRegex(version, semver_re)

        canonical = (repo_root / "spec" / "00_CANONICAL.md").read_text(encoding="utf-8")
        m = re.search(r"CANONICAL_SPEC_SEMVER:\s*`([^`]+)`", canonical)
        self.assertIsNotNone(m, "CANONICAL_SPEC_SEMVER not found in spec/00_CANONICAL.md")
        assert m is not None
        self.assertEqual(version, m.group(1))

        for cfg_path in ("configs/dev.yaml", "configs/prod.yaml"):
            cfg = yaml.safe_load((repo_root / cfg_path).read_text(encoding="utf-8"))
            self.assertEqual(version, str(cfg["pack"]["canonical_spec_semver"]))

        chart = yaml.safe_load((repo_root / "deploy" / "helm" / "ieim" / "Chart.yaml").read_text(encoding="utf-8"))
        self.assertEqual(version, str(chart["appVersion"]))
        self.assertEqual(version, str(chart["version"]))
