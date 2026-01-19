from __future__ import annotations

from pathlib import Path

from ieim.config import load_config
from ieim.auth.config import load_auth_config
from ieim.auth.rbac import load_rbac_config
from ieim.identity.config import load_identity_config
from ieim.observability.config import load_observability_config
from ieim.ops.retention import load_retention_config


def validate_config_file(*, path: Path) -> None:
    _ = load_config(path=path)
    _ = load_auth_config(path=path)
    _ = load_rbac_config(path=path)
    _ = load_identity_config(path=path)
    _ = load_observability_config(path=path)
    _ = load_retention_config(path=path)
