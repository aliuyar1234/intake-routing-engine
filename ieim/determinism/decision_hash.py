from __future__ import annotations

import hashlib
from typing import Any

from ieim.determinism.jcs import jcs_bytes


def decision_hash(obj: Any) -> str:
    """Compute a timestamp-free decision hash over a canonical decision input object."""

    return "sha256:" + hashlib.sha256(jcs_bytes(obj)).hexdigest()

