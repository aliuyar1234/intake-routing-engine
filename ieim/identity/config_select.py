from __future__ import annotations

from pathlib import Path


def select_config_path_for_message(*, repo_root: Path, normalized_message: dict) -> Path:
    """Select a config profile deterministically for a message.

    For the sample corpus, recipient domain determines the profile:
    - *@insure.example -> dev
    - otherwise -> prod
    """

    to_emails = normalized_message.get("to_emails") or []
    for addr in to_emails:
        if isinstance(addr, str) and addr.lower().endswith("@insure.example"):
            return repo_root / "configs" / "dev.yaml"
    return repo_root / "configs" / "prod.yaml"

