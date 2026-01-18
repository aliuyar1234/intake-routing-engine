from __future__ import annotations

import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional

from ieim.raw_store import sha256_prefixed


class AVScanner(ABC):
    @abstractmethod
    def scan(self, *, data: bytes, filename: str, mime_type: str) -> str:
        """Return an AV_STATUS_* string (CLEAN/INFECTED/SUSPICIOUS/FAILED)."""


class FixedStatusAVScanner(AVScanner):
    def __init__(self, status: str) -> None:
        self._status = status

    def scan(self, *, data: bytes, filename: str, mime_type: str) -> str:
        return self._status


class Sha256MappingAVScanner(AVScanner):
    def __init__(self, mapping: dict[str, str], *, default_status: str = "FAILED") -> None:
        self._mapping = dict(mapping)
        self._default = default_status

    def scan(self, *, data: bytes, filename: str, mime_type: str) -> str:
        return self._mapping.get(sha256_prefixed(data), self._default)


class ClamAVScanner(AVScanner):
    """ClamAV integration using the `clamscan` binary if present."""

    def __init__(self, *, clamscan_path: Optional[str] = None) -> None:
        self._clamscan_path = clamscan_path or shutil.which("clamscan")

    def scan(self, *, data: bytes, filename: str, mime_type: str) -> str:
        if not self._clamscan_path:
            return "FAILED"
        with tempfile.TemporaryDirectory() as td:
            path = Path(td) / filename
            path.write_bytes(data)
            try:
                proc = subprocess.run(
                    [self._clamscan_path, "--no-summary", str(path)],
                    capture_output=True,
                    text=True,
                    timeout=60,
                )
            except Exception:
                return "FAILED"
            if proc.returncode == 0:
                return "CLEAN"
            if proc.returncode == 1:
                return "INFECTED"
            return "FAILED"

