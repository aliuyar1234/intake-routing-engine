from __future__ import annotations

import unittest
from pathlib import Path

import yaml


class TestWorkflowsLint(unittest.TestCase):
    def test_workflows_are_valid_yaml(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        workflows_dir = repo_root / ".github" / "workflows"
        self.assertTrue(workflows_dir.is_dir(), "missing .github/workflows directory")

        workflow_files = sorted(list(workflows_dir.glob("*.yml")) + list(workflows_dir.glob("*.yaml")))
        self.assertGreater(len(workflow_files), 0, "no workflow files found")

        for path in workflow_files:
            data = yaml.safe_load(path.read_text(encoding="utf-8"))
            self.assertIsInstance(data, dict, f"workflow must be a mapping: {path.name}")
            self.assertIn("name", data, f"missing name: {path.name}")
            on_val = data.get("on", None)
            if on_val is None:
                on_val = data.get(True, None)  # YAML 1.1 'on' -> True if unquoted
            self.assertIsNotNone(on_val, f"missing on: {path.name}")
            jobs = data.get("jobs")
            self.assertIsInstance(jobs, dict, f"jobs must be a mapping: {path.name}")
            self.assertGreater(len(jobs), 0, f"jobs must not be empty: {path.name}")


if __name__ == "__main__":
    unittest.main()

