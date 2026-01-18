from __future__ import annotations

import hashlib
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import yaml


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _discover_pack_root(start: Path) -> Optional[Path]:
    for p in [start] + list(start.parents):
        if (p / "MANIFEST.sha256").is_file():
            return p
    return None


def _stable_repo_relative_path(path: Path) -> str:
    try:
        resolved = path.resolve()
    except Exception:
        return path.as_posix()

    root = _discover_pack_root(resolved)
    if root is None:
        return path.as_posix()
    try:
        return resolved.relative_to(root).as_posix()
    except Exception:
        return path.as_posix()


@dataclass(frozen=True)
class IdentityThresholds:
    confirmed_min_score: Decimal
    confirmed_min_margin: Decimal
    probable_min_score: Decimal
    probable_min_margin: Decimal


@dataclass(frozen=True)
class SignalSpec:
    weight: Decimal
    strength: Decimal


@dataclass(frozen=True)
class ScoreTransform:
    intercept: Decimal
    slope: Decimal


@dataclass(frozen=True)
class IdentityConfig:
    system_id: str
    canonical_spec_semver: str
    config_path: str
    config_sha256: str
    determinism_mode: bool
    top_k: int
    thresholds: IdentityThresholds
    shared_mailbox_penalty: Decimal
    signal_specs: dict[str, SignalSpec]
    score_transform: ScoreTransform


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
    return obj


def _require_decimal(obj: Any, *, path: str) -> Decimal:
    if isinstance(obj, (int, float, str)):
        return Decimal(str(obj))
    raise ValueError(f"{path} must be a number")


def load_identity_config(*, path: Path) -> IdentityConfig:
    data_bytes = path.read_bytes()
    cfg = yaml.safe_load(data_bytes.decode("utf-8"))
    cfg = _require_dict(cfg, path="config")

    pack = _require_dict(cfg.get("pack"), path="pack")
    system_id = _require_str(pack.get("system_id"), path="pack.system_id")
    canonical_spec_semver = _require_str(
        pack.get("canonical_spec_semver"), path="pack.canonical_spec_semver"
    )

    runtime = _require_dict(cfg.get("runtime"), path="runtime")
    determinism_mode = _require_bool(runtime.get("determinism_mode"), path="runtime.determinism_mode")

    identity = _require_dict(cfg.get("identity"), path="identity")
    top_k = _require_int(identity.get("top_k"), path="identity.top_k")
    shared_penalty = _require_decimal(
        identity.get("shared_mailbox_penalty"), path="identity.shared_mailbox_penalty"
    )

    thresholds_obj = _require_dict(identity.get("thresholds"), path="identity.thresholds")
    thresholds = IdentityThresholds(
        confirmed_min_score=_require_decimal(
            thresholds_obj.get("confirmed_min_score"),
            path="identity.thresholds.confirmed_min_score",
        ),
        confirmed_min_margin=_require_decimal(
            thresholds_obj.get("confirmed_min_margin"),
            path="identity.thresholds.confirmed_min_margin",
        ),
        probable_min_score=_require_decimal(
            thresholds_obj.get("probable_min_score"),
            path="identity.thresholds.probable_min_score",
        ),
        probable_min_margin=_require_decimal(
            thresholds_obj.get("probable_min_margin"),
            path="identity.thresholds.probable_min_margin",
        ),
    )

    weights_obj = _require_dict(identity.get("signal_weights"), path="identity.signal_weights")
    signal_specs: dict[str, SignalSpec] = {}
    for name, spec in weights_obj.items():
        name = _require_str(name, path="identity.signal_weights.<key>")
        spec_dict = _require_dict(spec, path=f"identity.signal_weights.{name}")
        signal_specs[name] = SignalSpec(
            weight=_require_decimal(spec_dict.get("weight"), path=f"identity.signal_weights.{name}.weight"),
            strength=_require_decimal(
                spec_dict.get("strength"), path=f"identity.signal_weights.{name}.strength"
            ),
        )

    scoring_obj = _require_dict(identity.get("scoring"), path="identity.scoring")
    score_transform = ScoreTransform(
        intercept=_require_decimal(scoring_obj.get("intercept"), path="identity.scoring.intercept"),
        slope=_require_decimal(scoring_obj.get("slope"), path="identity.scoring.slope"),
    )

    return IdentityConfig(
        system_id=system_id,
        canonical_spec_semver=canonical_spec_semver,
        config_path=_stable_repo_relative_path(path),
        config_sha256=_sha256_prefixed(data_bytes),
        determinism_mode=determinism_mode,
        top_k=top_k,
        thresholds=thresholds,
        shared_mailbox_penalty=shared_penalty,
        signal_specs=signal_specs,
        score_transform=score_transform,
    )
