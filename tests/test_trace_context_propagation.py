import re
import tempfile
import unittest
import urllib.request
from pathlib import Path

from ieim.api.app import ApiContext
from ieim.auth.config import load_auth_config
from ieim.auth.oidc import OidcJwtValidator
from ieim.auth.rbac import load_rbac_config
from ieim.observability import tracing
from ieim.observability.config import load_observability_config
from tests.api_test_server import run_api_server


class TestTraceContextPropagation(unittest.TestCase):
    def test_traceparent_header_is_propagated_to_response_trace_id(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]
        cfg_path = repo_root / "configs" / "dev.yaml"

        auth = load_auth_config(path=cfg_path)
        rbac = load_rbac_config(path=cfg_path)
        obs = load_observability_config(path=cfg_path)

        tracing.init_tracing(enabled=True, service_name="ieim-test")

        trace_id = "1" * 32
        parent_span_id = "2" * 16
        traceparent = f"00-{trace_id}-{parent_span_id}-01"

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
                req = urllib.request.Request(base_url + "/healthz", headers={"traceparent": traceparent})
                with urllib.request.urlopen(req, timeout=3) as resp:
                    self.assertEqual(int(resp.status), 200)
                    x_trace = resp.headers.get("X-Trace-Id") or ""
                    x_span = resp.headers.get("X-Span-Id") or ""

        self.assertEqual(x_trace, trace_id)
        self.assertTrue(re.fullmatch(r"[0-9a-f]{16}", x_span))


if __name__ == "__main__":
    unittest.main()

