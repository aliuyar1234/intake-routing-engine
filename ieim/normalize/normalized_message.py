from __future__ import annotations

import hashlib
import json
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from email import policy
from email.parser import BytesParser
from email.utils import getaddresses
from pathlib import Path
from typing import Optional


_WHITESPACE_RE = re.compile(r"[\\t\\r\\n]+")


@lru_cache(maxsize=1)
def _schema_id_and_version() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas" / "normalized_message.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str) or not schema_id:
        raise ValueError("normalized_message.schema.json missing $id")
    version = schema_id.rsplit(":", 1)[-1]
    return schema_id, version


def _format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


def _canonicalize_text(text: str) -> str:
    # Lowercasing keeps offsets stable for evidence spans.
    return text.lower()


def _strip_trailing_newlines(text: str) -> str:
    return text.rstrip("\r\n")


def _parse_single_address(value: Optional[str]) -> tuple[Optional[str], Optional[str]]:
    if not value:
        return None, None
    pairs = getaddresses([value])
    if not pairs:
        return None, None
    name, email = pairs[0]
    email = email.strip() if email else None
    name = name.strip() if name else None
    return email or None, name or None


def _parse_address_list(value: Optional[str]) -> list[str]:
    if not value:
        return []
    pairs = getaddresses([value])
    out: list[str] = []
    for _name, email in pairs:
        email = email.strip()
        if email:
            out.append(email)
    return out


def _extract_body_text(raw_mime: bytes) -> str:
    msg = BytesParser(policy=policy.default).parsebytes(raw_mime)
    body = msg.get_body(preferencelist=("plain",))
    if body is not None:
        return body.get_content()
    if msg.get_content_type() == "text/plain":
        return msg.get_content()
    return ""


def _detect_language(subject: str, body: str) -> str:
    text = _WHITESPACE_RE.sub(" ", f"{subject} {body}").lower()
    german_markers = ("guten tag", "bitte", "schaden", "polizz", "kündig", "rechnung")
    if any(m in text for m in german_markers):
        return "de"
    return "en"


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


@dataclass(frozen=True)
class ThreadKeys:
    internet_message_id: Optional[str]
    in_reply_to: Optional[str]
    conversation_id: Optional[str]


def _message_fingerprint(
    *,
    from_email: str,
    to_emails: list[str],
    cc_emails: list[str],
    subject_c14n: str,
    body_text_c14n: str,
    thread_keys: ThreadKeys,
    attachment_ids: list[str],
) -> str:
    canonical_obj = {
        "attachment_ids": sorted(attachment_ids),
        "body_text_c14n": body_text_c14n,
        "cc_emails": sorted(cc_emails),
        "from_email": from_email,
        "in_reply_to": thread_keys.in_reply_to or "",
        "internet_message_id": thread_keys.internet_message_id or "",
        "subject_c14n": subject_c14n,
        "to_emails": sorted(to_emails),
    }
    encoded = json.dumps(
        canonical_obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False
    ).encode("utf-8")
    return _sha256_prefixed(encoded)


def build_normalized_message(
    *,
    raw_mime: bytes,
    message_id: str,
    run_id: str,
    ingested_at: datetime,
    received_at: datetime,
    ingestion_source: str,
    raw_mime_uri: str,
    raw_mime_sha256: str,
    attachment_ids: list[str],
) -> dict:
    schema_id, schema_version = _schema_id_and_version()
    msg = BytesParser(policy=policy.default).parsebytes(raw_mime)

    from_email, from_display_name = _parse_single_address(msg.get("From"))
    if not from_email:
        raise ValueError("missing From address")

    to_emails = _parse_address_list(msg.get("To"))
    if not to_emails:
        raise ValueError("missing To address")

    cc_emails = _parse_address_list(msg.get("Cc"))

    reply_to, _reply_name = _parse_single_address(msg.get("Reply-To"))

    subject = str(msg.get("Subject") or "")
    body_text = _strip_trailing_newlines(_extract_body_text(raw_mime))

    subject_c14n = _canonicalize_text(subject)
    body_text_c14n = _canonicalize_text(body_text)

    thread_keys = ThreadKeys(
        internet_message_id=(str(msg.get("Message-ID")) if msg.get("Message-ID") else None),
        in_reply_to=(str(msg.get("In-Reply-To")) if msg.get("In-Reply-To") else None),
        conversation_id=None,
    )

    language = _detect_language(subject, body_text)
    fingerprint = _message_fingerprint(
        from_email=from_email,
        to_emails=to_emails,
        cc_emails=cc_emails,
        subject_c14n=subject_c14n,
        body_text_c14n=body_text_c14n,
        thread_keys=thread_keys,
        attachment_ids=attachment_ids,
    )

    return {
        "schema_id": schema_id,
        "schema_version": schema_version,
        "message_id": message_id,
        "run_id": run_id,
        "ingested_at": _format_datetime(ingested_at),
        "received_at": _format_datetime(received_at),
        "ingestion_source": ingestion_source,
        "raw_mime_uri": raw_mime_uri,
        "raw_mime_sha256": raw_mime_sha256,
        "from_email": from_email,
        "from_display_name": from_display_name,
        "reply_to_email": reply_to,
        "to_emails": to_emails,
        "cc_emails": cc_emails,
        "subject": subject,
        "subject_c14n": subject_c14n,
        "body_text": body_text,
        "body_text_c14n": body_text_c14n,
        "language": language,
        "thread_keys": {
            "internet_message_id": thread_keys.internet_message_id,
            "in_reply_to": thread_keys.in_reply_to,
            "conversation_id": thread_keys.conversation_id,
        },
        "attachment_ids": attachment_ids,
        "message_fingerprint": fingerprint,
    }
