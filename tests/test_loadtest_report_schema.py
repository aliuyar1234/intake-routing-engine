from __future__ import annotations

import json
import unittest
from pathlib import Path

import jsonschema

from ieim.ops.loadtest_profiles import run_profile


class TestLoadtestReportSchema(unittest.TestCase):
    def test_enterprise_smoke_report_matches_schema(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        report = run_profile(
            repo_root=repo_root,
            profile="enterprise_smoke",
            config_path=repo_root / "configs" / "dev.yaml",
            crm_mapping={"kunde1@example.test": ["45-1234567"]},
        )
        payload = report.to_dict()

        schema = json.loads((repo_root / "schemas" / "loadtest_report.schema.json").read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator.check_schema(schema)
        v = jsonschema.Draft202012Validator(schema)

        errors = sorted(v.iter_errors(payload), key=lambda e: list(e.path))
        if errors:
            self.fail(f"schema validation failed: {errors[0].message}")


if __name__ == "__main__":
    unittest.main()

