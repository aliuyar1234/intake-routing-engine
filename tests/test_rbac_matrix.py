import json
import tempfile
import unittest
import urllib.error
import urllib.request
from pathlib import Path

from ieim.api.app import ApiContext
from ieim.auth.config import AuthConfig, DirectGrantConfig, OIDCConfig
from ieim.auth.oidc import OidcJwtValidator
from ieim.auth.rbac import RbacConfig, RolePermissions
from ieim.hitl.review_store import FileReviewStore
from tests.api_test_server import run_api_server
from tests.oidc_test_server import run_oidc_test_server


def _http(method: str, url: str, *, headers: dict[str, str] | None = None) -> int:
    req = urllib.request.Request(url, method=method, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            _ = resp.read()
            return int(resp.status)
    except urllib.error.HTTPError as e:
        _ = e.read()
        return int(e.code)


class TestRbacMatrix(unittest.TestCase):
    def test_requires_auth_and_enforces_permissions(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with run_oidc_test_server() as oidc:
            rbac = RbacConfig(
                role_mappings={
                    "agent": RolePermissions(can_view_raw=False, can_view_audit=True, can_approve_drafts=False),
                    "reviewer": RolePermissions(can_view_raw=True, can_view_audit=True, can_approve_drafts=True),
                }
            )

            oidc_cfg = OIDCConfig(
                enabled=True,
                issuer_url=oidc.issuer_url,
                audience=None,
                actor_id_claim="sub",
                roles_claim="roles",
                role_name_map={},
                accepted_algorithms=("RS256",),
                leeway_seconds=0,
                http_timeout_seconds=2,
                direct_grant=DirectGrantConfig(enabled=False, client_id="ieim-ui", client_secret=None),
            )
            auth = AuthConfig(oidc=oidc_cfg)
            validator = OidcJwtValidator(config=oidc_cfg)

            with tempfile.TemporaryDirectory() as td:
                hitl_dir = Path(td) / "hitl"
                store = FileReviewStore(base_dir=hitl_dir)
                store.write(
                    item={
                        "review_item_id": "00000000-0000-0000-0000-000000000010",
                        "message_id": "00000000-0000-0000-0000-000000000020",
                        "run_id": "00000000-0000-0000-0000-000000000030",
                        "queue_id": "QUEUE_INTAKE_REVIEW_GENERAL",
                        "created_at": "2026-01-18T00:00:00Z",
                        "status": "OPEN",
                        "artifact_refs": [],
                        "draft_refs": [],
                    }
                )

                ctx = ApiContext(
                    repo_root=repo_root,
                    config_path=repo_root / "configs" / "dev.yaml",
                    auth=auth,
                    rbac=rbac,
                    oidc=validator,
                    hitl_dir=hitl_dir,
                    artifact_roots=(repo_root,),
                )

                with run_api_server(ctx=ctx) as base_url:
                    agent_token = oidc.issue_token(sub="agent1", roles=["agent"])
                    unmapped_token = oidc.issue_token(sub="user1", roles=["unknown_role"])

                    self.assertEqual(_http("GET", base_url + "/api/review/queues"), 401)
                    self.assertEqual(
                        _http("GET", base_url + "/api/review/queues", headers={"Authorization": f"Bearer {agent_token}"}),
                        200,
                    )
                    self.assertEqual(
                        _http("GET", base_url + "/api/review/queues", headers={"Authorization": f"Bearer {unmapped_token}"}),
                        403,
                    )

                    self.assertEqual(
                        _http(
                            "POST",
                            base_url + "/api/review/items/00000000-0000-0000-0000-000000000010/drafts/reply/approve",
                            headers={"Authorization": f"Bearer {agent_token}", "Idempotency-Key": "k1", "If-Match": "\"x\""},
                        ),
                        403,
                    )


if __name__ == "__main__":
    unittest.main()

