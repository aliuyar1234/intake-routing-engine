from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional, Sequence


def _require_dict(obj: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"{path} must be a mapping")
    return obj


def _require_str(obj: Any, *, path: str) -> str:
    if not isinstance(obj, str) or not obj:
        raise ValueError(f"{path} must be a non-empty string")
    return obj


def _require_bool(obj: Any, *, path: str) -> bool:
    if not isinstance(obj, bool):
        raise ValueError(f"{path} must be a boolean")
    return obj


def _require_int(obj: Any, *, path: str) -> int:
    if not isinstance(obj, int):
        raise ValueError(f"{path} must be an integer")
    return int(obj)


def _require_optional_str(obj: Any, *, path: str) -> Optional[str]:
    if obj is None:
        return None
    if not isinstance(obj, str) or not obj:
        raise ValueError(f"{path} must be a non-empty string or null")
    return obj


def _require_list_of_str(obj: Any, *, path: str) -> list[str]:
    if not isinstance(obj, list) or not all(isinstance(x, str) and x for x in obj):
        raise ValueError(f"{path} must be a list of non-empty strings")
    return list(obj)


def _require_str_map(obj: Any, *, path: str) -> dict[str, str]:
    if obj is None:
        return {}
    if not isinstance(obj, dict):
        raise ValueError(f"{path} must be a mapping")
    out: dict[str, str] = {}
    for k, v in obj.items():
        out[_require_str(k, path=f"{path}.<key>")] = _require_str(v, path=f"{path}.{k}")
    return out


@dataclass(frozen=True)
class DirectGrantConfig:
    enabled: bool
    client_id: str
    client_secret: Optional[str]


@dataclass(frozen=True)
class OIDCConfig:
    enabled: bool
    issuer_url: str
    audience: Optional[str]
    actor_id_claim: str
    roles_claim: str
    role_name_map: dict[str, str]
    accepted_algorithms: Sequence[str]
    leeway_seconds: int
    http_timeout_seconds: int
    direct_grant: DirectGrantConfig


@dataclass(frozen=True)
class AuthConfig:
    oidc: OIDCConfig


def load_auth_config(*, path: Path) -> AuthConfig:
    try:
        import yaml
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"PyYAML dependency unavailable: {e}") from e

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc = _require_dict(doc, path="config")

    auth = _require_dict(doc.get("auth"), path="auth")
    oidc = _require_dict(auth.get("oidc"), path="auth.oidc")

    enabled = _require_bool(oidc.get("enabled"), path="auth.oidc.enabled")
    issuer_url = _require_str(oidc.get("issuer_url"), path="auth.oidc.issuer_url")
    audience = _require_optional_str(oidc.get("audience"), path="auth.oidc.audience")

    actor_id_claim = str(oidc.get("actor_id_claim") or "sub")
    if not actor_id_claim or not isinstance(actor_id_claim, str):
        raise ValueError("auth.oidc.actor_id_claim must be a non-empty string")

    roles_claim = _require_str(oidc.get("roles_claim"), path="auth.oidc.roles_claim")
    role_name_map = _require_str_map(oidc.get("role_name_map"), path="auth.oidc.role_name_map")

    algs_raw = oidc.get("accepted_algorithms")
    accepted_algorithms = tuple(_require_list_of_str(algs_raw, path="auth.oidc.accepted_algorithms"))
    if not accepted_algorithms:
        raise ValueError("auth.oidc.accepted_algorithms must not be empty")

    leeway_seconds = _require_int(oidc.get("leeway_seconds"), path="auth.oidc.leeway_seconds")
    if leeway_seconds < 0:
        raise ValueError("auth.oidc.leeway_seconds must be >= 0")

    http_timeout_seconds = _require_int(
        oidc.get("http_timeout_seconds"), path="auth.oidc.http_timeout_seconds"
    )
    if http_timeout_seconds <= 0:
        raise ValueError("auth.oidc.http_timeout_seconds must be > 0")

    dg_obj = oidc.get("direct_grant") or {}
    dg = _require_dict(dg_obj, path="auth.oidc.direct_grant")
    dg_enabled = _require_bool(dg.get("enabled"), path="auth.oidc.direct_grant.enabled")
    dg_client_id = _require_str(dg.get("client_id"), path="auth.oidc.direct_grant.client_id")
    dg_client_secret = _require_optional_str(
        dg.get("client_secret"), path="auth.oidc.direct_grant.client_secret"
    )

    if enabled and issuer_url.lower() == "disabled":
        raise ValueError("auth.oidc.enabled=true requires a real auth.oidc.issuer_url")

    return AuthConfig(
        oidc=OIDCConfig(
            enabled=enabled,
            issuer_url=issuer_url,
            audience=audience,
            actor_id_claim=actor_id_claim,
            roles_claim=roles_claim,
            role_name_map=role_name_map,
            accepted_algorithms=accepted_algorithms,
            leeway_seconds=leeway_seconds,
            http_timeout_seconds=http_timeout_seconds,
            direct_grant=DirectGrantConfig(
                enabled=dg_enabled,
                client_id=dg_client_id,
                client_secret=dg_client_secret,
            ),
        )
    )


def dump_auth_config_debug(*, cfg: AuthConfig) -> str:
    """Return a JSON string safe to log (no secrets)."""
    redacted = {
        "oidc": {
            "enabled": cfg.oidc.enabled,
            "issuer_url": cfg.oidc.issuer_url,
            "audience": cfg.oidc.audience,
            "actor_id_claim": cfg.oidc.actor_id_claim,
            "roles_claim": cfg.oidc.roles_claim,
            "role_name_map": dict(cfg.oidc.role_name_map),
            "accepted_algorithms": list(cfg.oidc.accepted_algorithms),
            "leeway_seconds": cfg.oidc.leeway_seconds,
            "http_timeout_seconds": cfg.oidc.http_timeout_seconds,
            "direct_grant": {
                "enabled": cfg.oidc.direct_grant.enabled,
                "client_id": cfg.oidc.direct_grant.client_id,
                "client_secret": None if cfg.oidc.direct_grant.client_secret else None,
            },
        }
    }
    return json.dumps(redacted, ensure_ascii=False, sort_keys=True)
