import unittest

from ieim.auth.config import DirectGrantConfig, OIDCConfig
from ieim.auth.oidc import OidcJwtValidator
from tests.oidc_test_server import run_oidc_test_server


class TestAuthOidcJwtValidation(unittest.TestCase):
    def test_validates_jwt_and_supports_key_rotation(self) -> None:
        with run_oidc_test_server() as oidc:
            cfg = OIDCConfig(
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
            v = OidcJwtValidator(config=cfg)

            t1 = oidc.issue_token(sub="user123", roles=["reviewer"], kid="kid1")
            a1 = v.validate_bearer_token(token=t1)
            self.assertEqual(a1.actor_id, "user123")
            self.assertIn("reviewer", a1.roles)

            oidc.rotate_keys(kids=["kid2"])
            t2 = oidc.issue_token(sub="user123", roles=["reviewer"], kid="kid2")
            a2 = v.validate_bearer_token(token=t2)
            self.assertEqual(a2.actor_id, "user123")
            self.assertIn("reviewer", a2.roles)


if __name__ == "__main__":
    unittest.main()

