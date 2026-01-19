import tempfile
import unittest
import urllib.request
from pathlib import Path

from ieim.api.app import ApiContext
from ieim.auth.config import load_auth_config
from ieim.auth.oidc import OidcJwtValidator
from ieim.auth.rbac import load_rbac_config
from ieim.observability.config import load_observability_config
from tests.api_test_server import run_api_server


class TestMetricsExposed(unittest.TestCase):
    def test_api_metrics_endpoint_exposes_key_metrics(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cfg_path = repo_root / "configs" / "dev.yaml"

        auth = load_auth_config(path=cfg_path)
        rbac = load_rbac_config(path=cfg_path)
        obs = load_observability_config(path=cfg_path)

        with tempfile.TemporaryDirectory() as td:
            hitl_dir = Path(td) / "hitl"
            ctx = ApiContext(
                repo_root=repo_root,
                config_path=cfg_path,
                auth=auth,
                rbac=rbac,
                oidc=OidcJwtValidator(config=auth.oidc),
                hitl_dir=hitl_dir,
                artifact_roots=(repo_root,),
                observability=obs,
            )

            with run_api_server(ctx=ctx) as base_url:
                with urllib.request.urlopen(base_url + "/metrics", timeout=3) as resp:
                    body = resp.read().decode("utf-8", errors="replace")

        for name in (
            "emails_ingested_total",
            "emails_processed_total",
            "stage_latency_ms",
            "hitl_rate_percent",
            "mis_association_rate",
            "misroute_rate",
            "ocr_error_rate",
            "llm_cost_per_email",
        ):
            self.assertIn(name, body)


if __name__ == "__main__":
    unittest.main()
