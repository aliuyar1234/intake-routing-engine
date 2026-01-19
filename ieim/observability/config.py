from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any


def _require_dict(obj: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"{path} must be a mapping")
    return obj


def _require_bool(obj: Any, *, path: str) -> bool:
    if not isinstance(obj, bool):
        raise ValueError(f"{path} must be a boolean")
    return obj


@dataclass(frozen=True)
class ObservabilityConfig:
    metrics_enabled: bool
    tracing_enabled: bool


def load_observability_config(*, path: Path) -> ObservabilityConfig:
    try:
        import yaml
    except Exception as e:  # pragma: no cover
        raise RuntimeError(f"PyYAML dependency unavailable: {e}") from e

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc = _require_dict(doc, path="config")

    obs = doc.get("observability") or {}
    obs = _require_dict(obs, path="observability")

    metrics_enabled_raw = obs.get("metrics_enabled", False)
    tracing_enabled_raw = obs.get("tracing_enabled", False)

    return ObservabilityConfig(
        metrics_enabled=_require_bool(metrics_enabled_raw, path="observability.metrics_enabled"),
        tracing_enabled=_require_bool(tracing_enabled_raw, path="observability.tracing_enabled"),
    )

