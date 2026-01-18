import unittest
from pathlib import Path

from ieim.ops.load_test import run_load_test


class TestP8LoadTest(unittest.TestCase):
    def test_load_test_runs_on_sample_corpus(self) -> None:
        root = Path(__file__).resolve().parents[1]
        report = run_load_test(
            repo_root=root,
            normalized_dir=root / "data" / "samples" / "emails",
            attachments_dir=root / "data" / "samples" / "attachments",
            iterations=1,
            config_path=root / "configs" / "dev.yaml",
            crm_mapping={"kunde1@example.test": ["45-1234567"]},
        )
        self.assertEqual(report.status, "OK")
        self.assertGreaterEqual(report.messages, 1)
        self.assertEqual(report.stage_ms["IDENTITY"]["count"], report.messages)
        self.assertEqual(report.stage_ms["CLASSIFY"]["count"], report.messages)
        self.assertEqual(report.stage_ms["EXTRACT"]["count"], report.messages)
        self.assertEqual(report.stage_ms["ROUTE"]["count"], report.messages)


if __name__ == "__main__":
    unittest.main()

