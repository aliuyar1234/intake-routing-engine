from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable


def _require_dict(obj: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"{path} must be a mapping")
    return obj


def _require_bool(obj: Any, *, path: str) -> bool:
    if not isinstance(obj, bool):
        raise ValueError(f"{path} must be a boolean")
    return obj


def _require_str(obj: Any, *, path: str) -> str:
    if not isinstance(obj, str) or not obj:
        raise ValueError(f"{path} must be a non-empty string")
    return obj


@dataclass(frozen=True)
class RolePermissions:
    can_view_raw: bool
    can_view_audit: bool
    can_approve_drafts: bool

    def has(self, perm_name: str) -> bool:
        if perm_name == "can_view_raw":
            return self.can_view_raw
        if perm_name == "can_view_audit":
            return self.can_view_audit
        if perm_name == "can_approve_drafts":
            return self.can_approve_drafts
        raise ValueError(f"unknown permission: {perm_name}")

    def union(self, other: "RolePermissions") -> "RolePermissions":
        return RolePermissions(
            can_view_raw=self.can_view_raw or other.can_view_raw,
            can_view_audit=self.can_view_audit or other.can_view_audit,
            can_approve_drafts=self.can_approve_drafts or other.can_approve_drafts,
        )


@dataclass(frozen=True)
class RbacConfig:
    role_mappings: dict[str, RolePermissions]

    def permissions_for_roles(self, roles: Iterable[str]) -> RolePermissions:
        perms = RolePermissions(can_view_raw=False, can_view_audit=False, can_approve_drafts=False)
        for r in roles:
            cfg = self.role_mappings.get(r)
            if cfg is None:
                continue
            perms = perms.union(cfg)
        return perms


def load_rbac_config(*, path: Path) -> RbacConfig:
    try:
        import yaml
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"PyYAML dependency unavailable: {e}") from e

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc = _require_dict(doc, path="config")
    rbac = _require_dict(doc.get("rbac"), path="rbac")
    role_mappings = _require_dict(rbac.get("role_mappings"), path="rbac.role_mappings")

    out: dict[str, RolePermissions] = {}
    for role_key, perms in role_mappings.items():
        role = _require_str(role_key, path="rbac.role_mappings.<role>")
        perms_obj = _require_dict(perms, path=f"rbac.role_mappings.{role}")
        out[role] = RolePermissions(
            can_view_raw=_require_bool(
                perms_obj.get("can_view_raw"), path=f"rbac.role_mappings.{role}.can_view_raw"
            ),
            can_view_audit=_require_bool(
                perms_obj.get("can_view_audit"), path=f"rbac.role_mappings.{role}.can_view_audit"
            ),
            can_approve_drafts=_require_bool(
                perms_obj.get("can_approve_drafts"),
                path=f"rbac.role_mappings.{role}.can_approve_drafts",
            ),
        )

    if not out:
        raise ValueError("rbac.role_mappings must define at least one role")

    return RbacConfig(role_mappings=out)

