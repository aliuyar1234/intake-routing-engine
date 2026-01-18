from __future__ import annotations

from pathlib import Path

from ieim.config import load_config
from ieim.identity.config import load_identity_config
from ieim.ops.retention import load_retention_config


def validate_config_file(*, path: Path) -> None:
    _ = load_config(path=path)
    _ = load_identity_config(path=path)
    _ = load_retention_config(path=path)

