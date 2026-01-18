import tempfile
import unittest
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from ieim.api.app import ApiContext
from ieim.auth.config import AuthConfig, DirectGrantConfig, OIDCConfig
from ieim.auth.oidc import OidcJwtValidator
from ieim.auth.rbac import RbacConfig, RolePermissions
from ieim.hitl.review_store import FileReviewStore
from tests.api_test_server import run_api_server
from tests.oidc_test_server import run_oidc_test_server


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: A002
        return None


class TestUiSmoke(unittest.TestCase):
    def test_ui_login_and_queue_page_render(self) -> None:
        repo_root = Path(__file__).resolve().parents[1]

        with run_oidc_test_server() as oidc:
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
            rbac = RbacConfig(
                role_mappings={
                    "reviewer": RolePermissions(can_view_raw=True, can_view_audit=True, can_approve_drafts=True)
                }
            )

            with tempfile.TemporaryDirectory() as td:
                hitl_dir = Path(td) / "hitl"
                FileReviewStore(base_dir=hitl_dir).write(
                    item={
                        "review_item_id": "00000000-0000-0000-0000-000000000101",
                        "message_id": "00000000-0000-0000-0000-000000000102",
                        "run_id": "00000000-0000-0000-0000-000000000103",
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
                    # Login page renders.
                    with urllib.request.urlopen(base_url + "/ui/login", timeout=3) as resp:
                        html = resp.read().decode("utf-8", errors="replace")
                    self.assertIn("IEIM Login", html)

                    # Submit login via direct grant (expect 302 + Set-Cookie).
                    opener = urllib.request.build_opener(_NoRedirect)
                    form = urllib.parse.urlencode({"username": "reviewer", "password": "pw"}).encode("utf-8")
                    req = urllib.request.Request(
                        base_url + "/ui/login",
                        data=form,
                        method="POST",
                        headers={"Content-Type": "application/x-www-form-urlencoded"},
                    )

                    try:
                        _ = opener.open(req, timeout=3)
                        self.fail("expected redirect")
                    except urllib.error.HTTPError as e:
                        self.assertEqual(int(e.code), 302)
                        set_cookie = e.headers.get("Set-Cookie")
                        self.assertIsNotNone(set_cookie)
                        cookie_kv = str(set_cookie).split(";", 1)[0]
                        location = e.headers.get("Location") or ""
                        self.assertEqual(location, "/ui/queues")

                    # Authenticated queue page renders.
                    req = urllib.request.Request(
                        base_url + "/ui/queues",
                        method="GET",
                        headers={"Cookie": cookie_kv},
                    )
                    with urllib.request.urlopen(req, timeout=3) as resp:
                        html = resp.read().decode("utf-8", errors="replace")
                    self.assertIn("IEIM Queues", html)
                    self.assertIn("QUEUE_INTAKE_REVIEW_GENERAL", html)


if __name__ == "__main__":
    unittest.main()

