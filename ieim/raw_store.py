from __future__ import annotations

import hashlib
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


def sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class RawStorePutResult:
    uri: str
    sha256: str
    size_bytes: int


class FileRawStore:
    """Append-only, content-addressed raw store on a local filesystem."""

    def __init__(self, *, base_dir: Path) -> None:
        self._base_dir = base_dir

    def put_bytes(
        self,
        *,
        kind: str,
        data: bytes,
        file_extension: Optional[str] = None,
    ) -> RawStorePutResult:
        if not kind or "/" in kind or "\\" in kind:
            raise ValueError("kind must be a simple token")
        if file_extension and not file_extension.startswith("."):
            raise ValueError("file_extension must start with '.'")

        sha = sha256_prefixed(data)
        hex_hash = sha.split(":", 1)[1]
        ext = file_extension or ""

        rel = Path("raw_store") / kind / (hex_hash + ext)
        path = (self._base_dir / rel).resolve()
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            existing = path.read_bytes()
            if sha256_prefixed(existing) != sha:
                raise RuntimeError("immutability violation: existing content mismatch")
            return RawStorePutResult(uri=rel.as_posix(), sha256=sha, size_bytes=len(data))

        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return RawStorePutResult(uri=rel.as_posix(), sha256=sha, size_bytes=len(data))

    def get_bytes(self, *, uri: str) -> bytes:
        path = (self._base_dir / uri).resolve()
        return path.read_bytes()

