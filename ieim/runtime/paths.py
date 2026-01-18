from __future__ import annotations

from pathlib import Path


def discover_repo_root(start: Path) -> Path:
    for p in [start] + list(start.parents):
        if (p / "MANIFEST.sha256").is_file():
            return p
    raise RuntimeError(f"pack root not found from: {start}")

