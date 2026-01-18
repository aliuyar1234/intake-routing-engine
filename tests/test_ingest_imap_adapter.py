import unittest
from datetime import datetime, timezone
from email.message import EmailMessage

from ieim.ingest.adapter import MessageRef
from ieim.ingest.imap_adapter import ImapMailIngestAdapter


class _FakeImapClient:
    def __init__(self, *, uids: list[int], messages: dict[str, bytes]) -> None:
        self._uids = sorted(uids)
        self._messages = dict(messages)

    def login(self, _user: str, _password: str):
        return "OK", [b"logged-in"]

    def select(self, _mailbox: str, readonly: bool = True):
        if not readonly:
            return "NO", [b"readonly required"]
        return "OK", [b"selected"]

    def uid(self, command: str, *args):
        cmd = command.upper()
        if cmd == "SEARCH":
            if len(args) != 2:
                return "NO", [b"invalid search args"]
            _charset, criteria = args
            if not isinstance(criteria, str) or not criteria.startswith("UID "):
                return "NO", [b"invalid search"]
            range_part = criteria.split(" ", 1)[1]
            start_s, _end = range_part.split(":", 1)
            start = int(start_s)
            found = [u for u in self._uids if u >= start]
            return "OK", [" ".join(str(u) for u in found).encode("ascii")]
        if cmd == "FETCH":
            if len(args) != 2:
                return "NO", [b"invalid fetch args"]
            uid, _query = args
            uid = str(uid)
            raw = self._messages.get(uid)
            if raw is None:
                return "NO", [b"not found"]
            return "OK", [(f"{uid} (RFC822 {{{len(raw)}}})".encode("ascii"), raw)]
        return "NO", [b"unsupported"]

    def logout(self):
        return "OK", [b"bye"]


class TestImapMailIngestAdapter(unittest.TestCase):
    def test_list_message_refs_uses_uid_cursor(self) -> None:
        def factory():
            return _FakeImapClient(uids=[1, 2, 3, 10], messages={})

        adapter = ImapMailIngestAdapter(
            host="imap.example",
            username="user",
            password="pass",
            imap_factory=factory,
        )

        refs, cursor = adapter.list_message_refs(cursor=None, limit=2)
        self.assertEqual([r.source_message_id for r in refs], ["1", "2"])
        self.assertEqual(cursor, "2")

        refs, cursor = adapter.list_message_refs(cursor=cursor, limit=10)
        self.assertEqual([r.source_message_id for r in refs], ["3", "10"])
        self.assertEqual(cursor, "10")

    def test_fetch_raw_mime_returns_bytes(self) -> None:
        raw = b"From: a@example.com\nTo: b@example.com\nSubject: s\n\nbody\n"

        def factory():
            return _FakeImapClient(uids=[1], messages={"1": raw})

        adapter = ImapMailIngestAdapter(
            host="imap.example",
            username="user",
            password="pass",
            imap_factory=factory,
        )

        got = adapter.fetch_raw_mime(MessageRef(source_message_id="1"))
        self.assertEqual(got, raw)

    def test_received_at_parses_date(self) -> None:
        raw = (
            b"From: a@example.com\nTo: b@example.com\nSubject: s\n"
            b"Date: Fri, 17 Jan 2026 08:55:11 +0100\n\nbody\n"
        )

        def factory():
            return _FakeImapClient(uids=[1], messages={"1": raw})

        adapter = ImapMailIngestAdapter(
            host="imap.example",
            username="user",
            password="pass",
            imap_factory=factory,
        )

        received = adapter.get_received_at(MessageRef(source_message_id="1"))
        self.assertEqual(received, datetime(2026, 1, 17, 7, 55, 11, tzinfo=timezone.utc))

    def test_attachments_can_be_listed_and_fetched(self) -> None:
        msg = EmailMessage()
        msg["From"] = "a@example.com"
        msg["To"] = "b@example.com"
        msg["Subject"] = "s"
        msg["Date"] = "Fri, 17 Jan 2026 08:55:11 +0100"
        msg.set_content("hello")
        msg.add_attachment(b"abc", maintype="text", subtype="plain", filename="file.txt")
        raw = msg.as_bytes()

        def factory():
            return _FakeImapClient(uids=[1], messages={"1": raw})

        adapter = ImapMailIngestAdapter(
            host="imap.example",
            username="user",
            password="pass",
            imap_factory=factory,
        )

        attachments = list(adapter.list_attachments(MessageRef(source_message_id="1")))
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].attachment_id, "1:1")
        self.assertEqual(attachments[0].filename, "file.txt")

        att_bytes = adapter.fetch_attachment_bytes(attachments[0])
        self.assertEqual(att_bytes, b"abc")


if __name__ == "__main__":
    unittest.main()
