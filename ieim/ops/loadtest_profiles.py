from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ieim.ops.load_test import LoadTestReport, run_load_test


@dataclass(frozen=True)
class LoadTestProfile:
    name: str
    normalized_dir: str
    attachments_dir: str
    iterations: int


_PROFILES: dict[str, LoadTestProfile] = {
    "enterprise_smoke": LoadTestProfile(
        name="enterprise_smoke",
        normalized_dir="data/samples/emails",
        attachments_dir="data/samples/attachments",
        iterations=1,
    ),
}


def list_profiles() -> list[str]:
    return sorted(_PROFILES.keys())


def resolve_profile(name: str) -> LoadTestProfile:
    if not isinstance(name, str) or not name:
        raise ValueError("profile must be a non-empty string")
    p = _PROFILES.get(name)
    if p is None:
        raise ValueError(f"unknown loadtest profile: {name} (available: {list_profiles()})")
    return p


def run_profile(
    *,
    repo_root: Path,
    profile: str,
    config_path: Path | None,
    crm_mapping: dict[str, list[str]] | None,
) -> LoadTestReport:
    p = resolve_profile(profile)
    return run_load_test(
        repo_root=repo_root,
        normalized_dir=(repo_root / p.normalized_dir),
        attachments_dir=(repo_root / p.attachments_dir),
        iterations=int(p.iterations),
        profile=p.name,
        config_path=config_path,
        crm_mapping=crm_mapping,
    )

