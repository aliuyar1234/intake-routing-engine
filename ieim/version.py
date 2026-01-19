from __future__ import annotations

import re
from pathlib import Path

_SEMVER_RE = re.compile(
    r"^(0|[1-9]\d*)\.(0|[1-9]\d*)\.(0|[1-9]\d*)(?:-[0-9A-Za-z.-]+)?(?:\+[0-9A-Za-z.-]+)?$"
)


def read_repo_version(*, repo_root: Path) -> str:
    path = repo_root / "VERSION"
    if not path.is_file():
        raise FileNotFoundError("VERSION file not found at pack root")
    version = path.read_text(encoding="utf-8").strip()
    if not version:
        raise ValueError("VERSION file is empty")
    if _SEMVER_RE.match(version) is None:
        raise ValueError(f"VERSION is not valid SemVer: {version}")
    return version
