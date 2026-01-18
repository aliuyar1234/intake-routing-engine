from __future__ import annotations

import imaplib
from datetime import datetime, timezone
from email import policy
from email.message import Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from typing import Callable, Iterable, Optional

from ieim.ingest.adapter import AttachmentRef, MailIngestAdapter, MessageRef


ImapFactory = Callable[[], imaplib.IMAP4]


def _default_imap_factory(*, host: str, port: int, use_ssl: bool) -> ImapFactory:
    def _factory() -> imaplib.IMAP4:
        if use_ssl:
            return imaplib.IMAP4_SSL(host=host, port=port)
        return imaplib.IMAP4(host=host, port=port)

    return _factory


def _parse_imap_date(value: str) -> datetime:
    dt = parsedate_to_datetime(value)
    if dt is None:
        raise ValueError("invalid Date header")
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


def _parse_email(raw_mime: bytes) -> Message:
    return BytesParser(policy=policy.default).parsebytes(raw_mime)


class ImapMailIngestAdapter(MailIngestAdapter):
    """Mail ingestion adapter backed by IMAP (UID-based cursor)."""

    def __init__(
        self,
        *,
        host: str,
        username: str,
        password: str,
        mailbox: str = "INBOX",
        port: int = 993,
        use_ssl: bool = True,
        imap_factory: Optional[ImapFactory] = None,
    ) -> None:
        self._host = host
        self._username = username
        self._password = password
        self._mailbox = mailbox
        self._imap_factory = imap_factory or _default_imap_factory(
            host=host, port=port, use_ssl=use_ssl
        )

    def _with_client(self) -> imaplib.IMAP4:
        client = self._imap_factory()
        typ, _ = client.login(self._username, self._password)
        if typ != "OK":
            raise RuntimeError("imap login failed")
        typ, _ = client.select(self._mailbox, readonly=True)
        if typ != "OK":
            raise RuntimeError("imap select failed")
        return client

    def list_message_refs(
        self, *, cursor: Optional[str], limit: int
    ) -> tuple[list[MessageRef], Optional[str]]:
        if limit <= 0:
            raise ValueError("limit must be positive")

        start_uid = 1
        if cursor is not None:
            try:
                start_uid = int(cursor) + 1
            except ValueError as e:
                raise ValueError("cursor must be an integer UID string") from e

        client = self._with_client()
        try:
            typ, data = client.uid("SEARCH", None, f"UID {start_uid}:*")
            if typ != "OK" or not data:
                raise RuntimeError("imap search failed")
            raw_list = data[0] or b""
            uids = [u for u in raw_list.split() if u]
            selected = uids[:limit]
            refs = [MessageRef(source_message_id=u.decode("ascii")) for u in selected]
            new_cursor = cursor
            if selected:
                new_cursor = selected[-1].decode("ascii")
            return refs, new_cursor
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def fetch_raw_mime(self, ref: MessageRef) -> bytes:
        client = self._with_client()
        try:
            typ, data = client.uid("FETCH", ref.source_message_id, "(RFC822)")
            if typ != "OK" or not data:
                raise RuntimeError("imap fetch failed")
            for item in data:
                if isinstance(item, tuple) and len(item) >= 2 and isinstance(item[1], bytes):
                    return item[1]
            raise RuntimeError("imap fetch did not return RFC822 bytes")
        finally:
            try:
                client.logout()
            except Exception:
                pass

    def get_received_at(self, ref: MessageRef) -> datetime:
        msg = _parse_email(self.fetch_raw_mime(ref))
        date = msg.get("Date")
        if not isinstance(date, str) or not date:
            raise ValueError("missing Date header")
        return _parse_imap_date(date)

    def list_attachments(self, ref: MessageRef) -> Iterable[AttachmentRef]:
        msg = _parse_email(self.fetch_raw_mime(ref))
        out: list[AttachmentRef] = []
        idx = 0
        for part in msg.walk():
            if part.is_multipart():
                continue
            filename = part.get_filename()
            if not filename:
                continue
            payload = part.get_payload(decode=True) or b""
            idx += 1
            out.append(
                AttachmentRef(
                    attachment_id=f"{ref.source_message_id}:{idx}",
                    filename=str(filename),
                    mime_type=part.get_content_type(),
                    size_bytes=len(payload),
                )
            )
        return out

    def fetch_attachment_bytes(self, ref: AttachmentRef) -> bytes:
        if ":" not in ref.attachment_id:
            raise ValueError("invalid attachment reference")
        uid, idx_s = ref.attachment_id.split(":", 1)
        try:
            target = int(idx_s)
        except ValueError as e:
            raise ValueError("invalid attachment reference") from e

        msg = _parse_email(self.fetch_raw_mime(MessageRef(source_message_id=uid)))
        idx = 0
        for part in msg.walk():
            if part.is_multipart():
                continue
            filename = part.get_filename()
            if not filename:
                continue
            idx += 1
            if idx == target:
                return part.get_payload(decode=True) or b""
        raise KeyError("attachment not found")

