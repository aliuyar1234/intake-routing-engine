from __future__ import annotations

import json
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Optional, Sequence

from ieim.auth.config import OIDCConfig


class OIDCDiscoveryError(RuntimeError):
    pass


class OIDCTokenValidationError(RuntimeError):
    pass


@dataclass(frozen=True)
class OIDCProviderMetadata:
    issuer: str
    jwks_uri: str
    token_endpoint: str


def _fetch_json(*, url: str, timeout_seconds: int) -> dict[str, Any]:
    req = urllib.request.Request(
        url,
        method="GET",
        headers={"Accept": "application/json"},
    )
    try:
        with urllib.request.urlopen(req, timeout=float(timeout_seconds)) as resp:
            raw = resp.read()
    except urllib.error.HTTPError as e:
        raise OIDCDiscoveryError(f"HTTP {e.code} fetching {url}") from e
    except Exception as e:
        raise OIDCDiscoveryError(f"failed to fetch {url}: {type(e).__name__}: {e}") from e

    try:
        obj = json.loads(raw.decode("utf-8"))
    except Exception as e:
        raise OIDCDiscoveryError(f"invalid JSON from {url}") from e

    if not isinstance(obj, dict):
        raise OIDCDiscoveryError(f"invalid discovery JSON shape from {url}")
    return obj


def _discover(*, issuer_url: str, timeout_seconds: int) -> OIDCProviderMetadata:
    issuer_url = issuer_url.rstrip("/")
    url = issuer_url + "/.well-known/openid-configuration"
    doc = _fetch_json(url=url, timeout_seconds=timeout_seconds)

    issuer = doc.get("issuer")
    jwks_uri = doc.get("jwks_uri")
    token_endpoint = doc.get("token_endpoint")
    if not isinstance(issuer, str) or not issuer:
        raise OIDCDiscoveryError("discovery missing issuer")
    if not isinstance(jwks_uri, str) or not jwks_uri:
        raise OIDCDiscoveryError("discovery missing jwks_uri")
    if not isinstance(token_endpoint, str) or not token_endpoint:
        raise OIDCDiscoveryError("discovery missing token_endpoint")

    return OIDCProviderMetadata(issuer=issuer, jwks_uri=jwks_uri, token_endpoint=token_endpoint)


def _get_by_dotted_path(obj: Any, path: str) -> Any:
    if not path:
        raise ValueError("claim path must be non-empty")
    cur: Any = obj
    for seg in path.split("."):
        if not seg:
            raise ValueError(f"invalid claim path segment in: {path}")
        if isinstance(cur, dict):
            cur = cur.get(seg)
        else:
            return None
    return cur


@dataclass(frozen=True)
class AuthenticatedActor:
    actor_id: str
    roles: Sequence[str]
    claims: dict[str, Any]


class OidcJwtValidator:
    def __init__(self, *, config: OIDCConfig) -> None:
        self._config = config
        self._meta: Optional[OIDCProviderMetadata] = None
        self._jwks_client = None

    def _require_pyjwt(self):
        try:
            import jwt  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("PyJWT is required for OIDC JWT validation (requirements/runtime.txt)") from e
        return jwt

    def _metadata(self) -> OIDCProviderMetadata:
        if self._meta is not None:
            return self._meta
        self._meta = _discover(issuer_url=self._config.issuer_url, timeout_seconds=self._config.http_timeout_seconds)
        return self._meta

    def _jwks(self):
        if self._jwks_client is not None:
            return self._jwks_client

        jwt = self._require_pyjwt()
        meta = self._metadata()
        self._jwks_client = jwt.PyJWKClient(meta.jwks_uri, timeout=float(self._config.http_timeout_seconds))
        return self._jwks_client

    def validate_bearer_token(self, *, token: str) -> AuthenticatedActor:
        if not self._config.enabled:
            raise OIDCTokenValidationError("OIDC disabled")
        if not token:
            raise OIDCTokenValidationError("empty token")

        jwt = self._require_pyjwt()
        try:
            signing_key = self._jwks().get_signing_key_from_jwt(token).key
        except Exception as e:
            raise OIDCTokenValidationError(f"unable to resolve signing key: {type(e).__name__}") from e

        options: dict[str, Any] = {}
        if self._config.audience is None:
            options["verify_aud"] = False

        try:
            claims = jwt.decode(
                token,
                signing_key,
                algorithms=list(self._config.accepted_algorithms),
                audience=self._config.audience,
                issuer=self._config.issuer_url.rstrip("/"),
                options=options,
                leeway=int(self._config.leeway_seconds),
            )
        except Exception as e:
            raise OIDCTokenValidationError(f"invalid token: {type(e).__name__}") from e

        if not isinstance(claims, dict):
            raise OIDCTokenValidationError("decoded claims is not an object")

        actor_id_raw = claims.get(self._config.actor_id_claim)
        if not isinstance(actor_id_raw, str) or not actor_id_raw:
            raise OIDCTokenValidationError(f"missing actor_id claim: {self._config.actor_id_claim}")
        actor_id = actor_id_raw

        roles_raw = _get_by_dotted_path(claims, self._config.roles_claim)
        roles: list[str] = []
        if isinstance(roles_raw, list) and all(isinstance(r, str) and r for r in roles_raw):
            roles = list(roles_raw)
        elif isinstance(roles_raw, str) and roles_raw:
            roles = [roles_raw]

        mapped: list[str] = []
        for r in roles:
            mapped.append(self._config.role_name_map.get(r, r))

        mapped_sorted = tuple(sorted(set(mapped)))
        return AuthenticatedActor(actor_id=actor_id, roles=mapped_sorted, claims=dict(claims))

    def direct_grant_password(self, *, username: str, password: str) -> str:
        if not self._config.direct_grant.enabled:
            raise OIDCDiscoveryError("direct grant disabled")
        if not username or not password:
            raise ValueError("username and password must be non-empty")

        meta = self._metadata()
        form = {
            "grant_type": "password",
            "client_id": self._config.direct_grant.client_id,
            "username": username,
            "password": password,
        }
        if self._config.direct_grant.client_secret is not None:
            form["client_secret"] = self._config.direct_grant.client_secret

        body = urllib.parse.urlencode(form).encode("utf-8")
        req = urllib.request.Request(
            meta.token_endpoint,
            method="POST",
            data=body,
            headers={"Content-Type": "application/x-www-form-urlencoded", "Accept": "application/json"},
        )
        try:
            with urllib.request.urlopen(req, timeout=float(self._config.http_timeout_seconds)) as resp:
                raw = resp.read()
        except urllib.error.HTTPError as e:
            raise OIDCDiscoveryError(f"HTTP {e.code} from token endpoint") from e
        except Exception as e:
            raise OIDCDiscoveryError(f"failed to call token endpoint: {type(e).__name__}: {e}") from e

        try:
            obj = json.loads(raw.decode("utf-8"))
        except Exception as e:
            raise OIDCDiscoveryError("invalid JSON from token endpoint") from e
        if not isinstance(obj, dict):
            raise OIDCDiscoveryError("invalid token endpoint response shape")

        access_token = obj.get("access_token")
        if not isinstance(access_token, str) or not access_token:
            raise OIDCDiscoveryError("token endpoint did not return access_token")
        return access_token
