from __future__ import annotations

import base64
import json
import time
import urllib.parse
from contextlib import contextmanager
from dataclasses import dataclass
from http.server import BaseHTTPRequestHandler, HTTPServer
from threading import Thread
from typing import Any, Optional


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _b64url_uint(n: int) -> str:
    if n < 0:
        raise ValueError("n must be >= 0")
    if n == 0:
        return _b64url(b"\x00")
    b = n.to_bytes((n.bit_length() + 7) // 8, "big")
    return _b64url(b)


@dataclass
class OidcTestKey:
    kid: str
    private_key: Any
    jwk_public: dict[str, Any]


def _generate_rsa_key(*, kid: str) -> OidcTestKey:
    try:
        from cryptography.hazmat.primitives.asymmetric import rsa  # type: ignore
    except Exception as e:  # pragma: no cover
        raise RuntimeError("cryptography is required for OIDC tests") from e

    private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
    pub = private_key.public_key().public_numbers()
    jwk = {
        "kty": "RSA",
        "kid": kid,
        "use": "sig",
        "alg": "RS256",
        "n": _b64url_uint(int(pub.n)),
        "e": _b64url_uint(int(pub.e)),
    }
    return OidcTestKey(kid=kid, private_key=private_key, jwk_public=jwk)


class _OidcServer(HTTPServer):
    issuer_url: str
    keys: list[OidcTestKey]
    user_roles: dict[str, list[str]]

    def __init__(self, server_address: tuple[str, int]):
        super().__init__(server_address, _OidcHandler)
        host, port = self.server_address
        self.issuer_url = f"http://{host}:{port}"
        self.keys = [_generate_rsa_key(kid="kid1")]
        self.user_roles = {"reviewer": ["reviewer"], "privacy": ["privacy_officer"], "admin": ["administrator"]}

    def jwks(self) -> dict[str, Any]:
        return {"keys": [k.jwk_public for k in self.keys]}

    def issue_token(self, *, sub: str, roles: list[str], kid: Optional[str] = None) -> str:
        try:
            import jwt  # type: ignore
        except Exception as e:  # pragma: no cover
            raise RuntimeError("PyJWT is required for OIDC tests") from e

        now = int(time.time())
        claims = {
            "iss": self.issuer_url,
            "sub": sub,
            "iat": now,
            "exp": now + 3600,
            "roles": list(roles),
        }

        key = self.keys[0]
        if kid is not None:
            for k in self.keys:
                if k.kid == kid:
                    key = k
                    break
        return str(jwt.encode(claims, key.private_key, algorithm="RS256", headers={"kid": key.kid}))

    def rotate_keys(self, *, kids: list[str]) -> None:
        self.keys = [_generate_rsa_key(kid=k) for k in kids]


class _OidcHandler(BaseHTTPRequestHandler):
    def log_message(self, format: str, *args: Any) -> None:  # noqa: A002
        return

    def _send_json(self, status: int, obj: Any) -> None:
        payload = json.dumps(obj, ensure_ascii=False).encode("utf-8")
        self.send_response(int(status))
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_GET(self) -> None:  # noqa: N802
        srv = self.server
        assert isinstance(srv, _OidcServer)

        if self.path == "/.well-known/openid-configuration":
            self._send_json(
                200,
                {
                    "issuer": srv.issuer_url,
                    "jwks_uri": srv.issuer_url + "/jwks",
                    "token_endpoint": srv.issuer_url + "/token",
                },
            )
            return

        if self.path == "/jwks":
            self._send_json(200, srv.jwks())
            return

        self._send_json(404, {"error": "NOT_FOUND"})

    def do_POST(self) -> None:  # noqa: N802
        srv = self.server
        assert isinstance(srv, _OidcServer)

        if self.path != "/token":
            self._send_json(404, {"error": "NOT_FOUND"})
            return

        length = int(self.headers.get("Content-Length") or "0")
        raw = self.rfile.read(length).decode("utf-8", errors="replace")
        form = urllib.parse.parse_qs(raw, keep_blank_values=True)
        grant_type = (form.get("grant_type") or [""])[0]
        username = (form.get("username") or [""])[0]
        password = (form.get("password") or [""])[0]
        client_id = (form.get("client_id") or [""])[0]

        if grant_type != "password" or not username or not password or not client_id:
            self._send_json(400, {"error": "invalid_request"})
            return

        roles = srv.user_roles.get(username, ["reviewer"])
        token = srv.issue_token(sub=username, roles=roles)
        self._send_json(200, {"access_token": token, "token_type": "Bearer", "expires_in": 3600})


@contextmanager
def run_oidc_test_server():
    srv = _OidcServer(("127.0.0.1", 0))
    t = Thread(target=srv.serve_forever, kwargs={"poll_interval": 0.05}, daemon=True)
    t.start()
    try:
        yield srv
    finally:
        srv.shutdown()
        srv.server_close()
        t.join(timeout=2)
