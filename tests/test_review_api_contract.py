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


def _http_json(method: str, url: str, *, headers: dict[str, str] | None = None, body: dict | None = None):
    data = None
    if body is not None:
        data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    if body is not None:
        req.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(req, timeout=3) as resp:
            raw = resp.read().decode("utf-8", errors="replace")
            return resp.status, dict(resp.headers), raw
    except urllib.error.HTTPError as e:
        raw = e.read().decode("utf-8", errors="replace")
        return int(e.code), dict(e.headers), raw


class TestReviewApiContract(unittest.TestCase):
    def test_review_api_endpoints_exist_and_are_consistent(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with run_oidc_test_server() as oidc:
            rbac = RbacConfig(
                role_mappings={
                    "agent": RolePermissions(can_view_raw=False, can_view_audit=True, can_approve_drafts=False),
                    "reviewer": RolePermissions(can_view_raw=True, can_view_audit=True, can_approve_drafts=True),
                    "privacy_officer": RolePermissions(can_view_raw=True, can_view_audit=True, can_approve_drafts=True),
                    "administrator": RolePermissions(can_view_raw=True, can_view_audit=True, can_approve_drafts=True),
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
                direct_grant=DirectGrantConfig(enabled=True, client_id="ieim-ui", client_secret=None),
            )
            auth = AuthConfig(oidc=oidc_cfg)
            validator = OidcJwtValidator(config=oidc_cfg)

            with tempfile.TemporaryDirectory() as td:
                hitl_dir = Path(td) / "hitl"
                store = FileReviewStore(base_dir=hitl_dir)

                review_item_id = "00000000-0000-0000-0000-000000000001"
                review_item = {
                    "review_item_id": review_item_id,
                    "message_id": "00000000-0000-0000-0000-000000000002",
                    "run_id": "00000000-0000-0000-0000-000000000003",
                    "queue_id": "QUEUE_PRIVACY_DSR",
                    "created_at": "2026-01-18T00:00:00Z",
                    "status": "OPEN",
                    "artifact_refs": [],
                    "draft_refs": [
                        {
                            "schema_id": "DRAFT_REQUEST_INFO",
                            "uri": "request_info.md",
                            "sha256": "sha256:" + ("0" * 64),
                        }
                    ],
                }
                store.write(item=review_item)

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
                    reviewer_token = oidc.issue_token(sub="reviewer1", roles=["reviewer"])
                    privacy_token = oidc.issue_token(sub="privacy1", roles=["privacy_officer"])

                    # Unauthenticated -> 401
                    st, _hdrs, _raw = _http_json("GET", base_url + "/api/review/queues")
                    self.assertEqual(st, 401)

                    # List queues -> 200
                    st, _hdrs, raw = _http_json(
                        "GET",
                        base_url + "/api/review/queues",
                        headers={"Authorization": f"Bearer {reviewer_token}"},
                    )
                    self.assertEqual(st, 200)
                    doc = json.loads(raw)
                    self.assertIn("queues", doc)

                    # Get item -> ETag present
                    st, hdrs, raw = _http_json(
                        "GET",
                        base_url + f"/api/review/items/{review_item_id}",
                        headers={"Authorization": f"Bearer {reviewer_token}"},
                    )
                    self.assertEqual(st, 200)
                    self.assertIn("ETag", hdrs)
                    etag = hdrs["ETag"].strip().strip('"')
                    doc = json.loads(raw)
                    self.assertIn("review_item", doc)

                    # Submit correction requires Idempotency-Key + If-Match
                    st, _hdrs, _raw = _http_json(
                        "POST",
                        base_url + f"/api/review/items/{review_item_id}/corrections",
                        headers={"Authorization": f"Bearer {reviewer_token}", "If-Match": etag},
                        body={"corrections": []},
                    )
                    self.assertEqual(st, 400)

                    corrections = [
                        {
                            "target_stage": "ROUTE",
                            "patch": [{"op": "replace", "path": "/queue_id", "value": "QUEUE_INTAKE_REVIEW_GENERAL"}],
                            "justification": "test",
                            "evidence": [],
                        }
                    ]
                    st, _hdrs, raw = _http_json(
                        "POST",
                        base_url + f"/api/review/items/{review_item_id}/corrections",
                        headers={
                            "Authorization": f"Bearer {reviewer_token}",
                            "If-Match": etag,
                            "Idempotency-Key": "k1",
                        },
                        body={"corrections": corrections, "note": "test"},
                    )
                    self.assertEqual(st, 200)
                    resp1 = json.loads(raw)
                    self.assertIn("correction_id", resp1)

                    # Same idempotency key -> same correction_id
                    st, _hdrs, raw = _http_json(
                        "POST",
                        base_url + f"/api/review/items/{review_item_id}/corrections",
                        headers={
                            "Authorization": f"Bearer {reviewer_token}",
                            "If-Match": etag,
                            "Idempotency-Key": "k1",
                        },
                        body={"corrections": corrections, "note": "test"},
                    )
                    self.assertEqual(st, 200)
                    resp2 = json.loads(raw)
                    self.assertEqual(resp1["correction_id"], resp2["correction_id"])

                    # Privacy drafts: reviewer cannot approve in privacy queue; privacy_officer can.
                    st, _hdrs, _raw = _http_json(
                        "POST",
                        base_url + f"/api/review/items/{review_item_id}/drafts/request_info/approve",
                        headers={
                            "Authorization": f"Bearer {reviewer_token}",
                            "If-Match": etag,
                            "Idempotency-Key": "k2",
                        },
                        body=None,
                    )
                    self.assertEqual(st, 403)

                    st, _hdrs, raw = _http_json(
                        "POST",
                        base_url + f"/api/review/items/{review_item_id}/drafts/request_info/approve",
                        headers={
                            "Authorization": f"Bearer {privacy_token}",
                            "If-Match": etag,
                            "Idempotency-Key": "k3",
                        },
                        body=None,
                    )
                    self.assertEqual(st, 200)
                    self.assertEqual(json.loads(raw).get("status"), "OK")


if __name__ == "__main__":
    unittest.main()
