from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable, Optional

from ieim.ingest.adapter import AttachmentRef, MailIngestAdapter, MessageRef


def _discover_pack_root(start: Path) -> Optional[Path]:
    for p in [start] + list(start.parents):
        if (p / "MANIFEST.sha256").is_file():
            return p
    return None


def _parse_iso_datetime(value: str) -> datetime:
    v = value.strip()
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    try:
        dt = datetime.fromisoformat(v)
    except ValueError:
        dt = parsedate_to_datetime(v)
        if dt is None:
            raise
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


@dataclass(frozen=True)
class _AttachmentInfo:
    ref: AttachmentRef
    bytes_path: Path


class FilesystemMailIngestAdapter(MailIngestAdapter):
    """Reads messages and attachments from directories on disk.

    This adapter is intended for local development and for running the sample corpus.
    """

    def __init__(
        self,
        *,
        raw_mime_dir: Path,
        attachments_dir: Path,
        pack_root: Optional[Path] = None,
    ) -> None:
        self._raw_mime_dir = raw_mime_dir
        self._attachments_dir = attachments_dir
        self._pack_root = (
            pack_root
            or _discover_pack_root(raw_mime_dir)
            or _discover_pack_root(attachments_dir)
        )

        self._message_ids = sorted(
            p.stem for p in self._raw_mime_dir.glob("*.eml") if p.is_file()
        )
        self._attachments_by_message_id: dict[str, list[_AttachmentInfo]] = {}
        self._attachment_bytes_by_id: dict[str, Path] = {}

        for artifact_path in self._attachments_dir.glob("*.artifact.json"):
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            message_id = artifact.get("message_id")
            attachment_id = artifact.get("attachment_id")
            filename = artifact.get("filename")
            mime_type = artifact.get("mime_type")
            size_bytes = artifact.get("size_bytes")
            extracted_text_uri = artifact.get("extracted_text_uri")

            if not isinstance(message_id, str) or not isinstance(attachment_id, str):
                raise ValueError(f"invalid attachment artifact: {artifact_path.as_posix()}")
            if not isinstance(filename, str) or not isinstance(mime_type, str):
                raise ValueError(f"invalid attachment artifact: {artifact_path.as_posix()}")
            if not isinstance(size_bytes, int):
                raise ValueError(f"invalid attachment artifact: {artifact_path.as_posix()}")
            if not isinstance(extracted_text_uri, str):
                raise ValueError(f"invalid attachment artifact: {artifact_path.as_posix()}")

            bytes_path = Path(extracted_text_uri)
            if not bytes_path.is_absolute():
                if self._pack_root is None:
                    raise ValueError(
                        "pack_root is required to resolve relative attachment URIs"
                    )
                bytes_path = (self._pack_root / bytes_path).resolve()

            ref = AttachmentRef(
                attachment_id=attachment_id,
                filename=filename,
                mime_type=mime_type,
                size_bytes=size_bytes,
            )

            self._attachment_bytes_by_id[attachment_id] = bytes_path
            self._attachments_by_message_id.setdefault(message_id, []).append(
                _AttachmentInfo(ref=ref, bytes_path=bytes_path)
            )

        for msg_id, infos in self._attachments_by_message_id.items():
            self._attachments_by_message_id[msg_id] = sorted(
                infos, key=lambda x: x.ref.attachment_id
            )

    def list_message_refs(
        self, *, cursor: Optional[str], limit: int
    ) -> tuple[list[MessageRef], Optional[str]]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        if cursor is None:
            ids = self._message_ids
        else:
            ids = [mid for mid in self._message_ids if mid > cursor]

        selected = ids[:limit]
        refs = [MessageRef(source_message_id=mid) for mid in selected]
        new_cursor = selected[-1] if selected else cursor
        return refs, new_cursor

    def fetch_raw_mime(self, ref: MessageRef) -> bytes:
        path = self._raw_mime_dir / f"{ref.source_message_id}.eml"
        return path.read_bytes()

    def get_received_at(self, ref: MessageRef) -> datetime:
        raw = self.fetch_raw_mime(ref)
        header_text = raw.split(b"\n\n", 1)[0].decode("utf-8", errors="replace")
        for line in header_text.splitlines():
            if line.lower().startswith("date:"):
                return _parse_iso_datetime(line.split(":", 1)[1])
        raise ValueError("missing Date header")

    def list_attachments(self, ref: MessageRef) -> Iterable[AttachmentRef]:
        infos = self._attachments_by_message_id.get(ref.source_message_id, [])
        return [info.ref for info in infos]

    def fetch_attachment_bytes(self, ref: AttachmentRef) -> bytes:
        path = self._attachment_bytes_by_id.get(ref.attachment_id)
        if path is None:
            raise KeyError(f"unknown attachment_id: {ref.attachment_id}")
        return path.read_bytes()
