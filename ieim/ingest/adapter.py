from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Iterable, Optional


@dataclass(frozen=True)
class MessageRef:
    source_message_id: str


@dataclass(frozen=True)
class AttachmentRef:
    attachment_id: str
    filename: str
    mime_type: str
    size_bytes: int


class MailIngestAdapter(ABC):
    """Adapter boundary for inbound email sources."""

    @abstractmethod
    def list_message_refs(
        self, *, cursor: Optional[str], limit: int
    ) -> tuple[list[MessageRef], Optional[str]]:
        """Return up to `limit` new message refs and a new cursor."""

    @abstractmethod
    def fetch_raw_mime(self, ref: MessageRef) -> bytes:
        """Return raw RFC822 / MIME bytes for a message."""

    @abstractmethod
    def get_received_at(self, ref: MessageRef) -> datetime:
        """Return the message received timestamp from the source system."""

    @abstractmethod
    def list_attachments(self, ref: MessageRef) -> Iterable[AttachmentRef]:
        """Return attachment references for a message."""

    @abstractmethod
    def fetch_attachment_bytes(self, ref: AttachmentRef) -> bytes:
        """Return the raw bytes for an attachment."""

