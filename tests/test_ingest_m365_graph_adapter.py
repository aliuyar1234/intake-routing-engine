import base64
import json
import unittest
from datetime import datetime, timezone

from ieim.ingest.adapter import MessageRef
from ieim.ingest.m365_graph_adapter import M365GraphMailIngestAdapter


class _FakeRequester:
    def __init__(self, responses: dict[str, bytes]) -> None:
        self._responses = responses
        self.calls: list[tuple[str, dict[str, str]]] = []

    def __call__(self, url: str, headers: dict[str, str]) -> bytes:
        self.calls.append((url, dict(headers)))
        if url not in self._responses:
            raise KeyError(f"unexpected url: {url}")
        return self._responses[url]


class TestM365GraphMailIngestAdapter(unittest.TestCase):
    def test_delta_pagination_and_cursor_progression(self) -> None:
        base_url = "https://graph.example/v1.0"
        start_url = (
            f"{base_url}/users/user123/mailFolders/Inbox/messages/delta"
            "?%24select=id%2CreceivedDateTime&%24top=2"
        )

        next_1 = "https://next/1"
        next_2 = "https://next/2"
        delta_1 = "https://delta/1"

        responses = {
            start_url: json.dumps(
                {
                    "value": [
                        {"id": "m1", "receivedDateTime": "2026-01-17T07:55:11Z"},
                        {"id": "m2", "receivedDateTime": "2026-01-17T07:56:11Z"},
                    ],
                    "@odata.nextLink": next_1,
                }
            ).encode("utf-8"),
            next_1: json.dumps(
                {
                    "value": [
                        {"id": "m3", "receivedDateTime": "2026-01-17T07:57:11Z"},
                        {"id": "m4", "receivedDateTime": "2026-01-17T07:58:11Z"},
                    ],
                    "@odata.nextLink": next_2,
                }
            ).encode("utf-8"),
            next_2: json.dumps(
                {
                    "value": [{"id": "m5", "receivedDateTime": "2026-01-17T07:59:11Z"}],
                    "@odata.deltaLink": delta_1,
                }
            ).encode("utf-8"),
            delta_1: json.dumps({"value": [], "@odata.deltaLink": delta_1}).encode("utf-8"),
        }

        requester = _FakeRequester(responses)
        adapter = M365GraphMailIngestAdapter(
            user_id="user123",
            access_token_provider=lambda: "TOKEN",
            folder_id="Inbox",
            base_url=base_url,
            request_bytes=requester,
        )

        refs, cursor = adapter.list_message_refs(cursor=None, limit=2)
        self.assertEqual([r.source_message_id for r in refs], ["m1", "m2"])
        self.assertEqual(cursor, next_1)

        refs, cursor = adapter.list_message_refs(cursor=cursor, limit=2)
        self.assertEqual([r.source_message_id for r in refs], ["m3", "m4"])
        self.assertEqual(cursor, next_2)

        refs, cursor = adapter.list_message_refs(cursor=cursor, limit=2)
        self.assertEqual([r.source_message_id for r in refs], ["m5"])
        self.assertEqual(cursor, delta_1)

        refs, cursor = adapter.list_message_refs(cursor=cursor, limit=2)
        self.assertEqual(refs, [])
        self.assertEqual(cursor, delta_1)

        for _, headers in requester.calls:
            self.assertEqual(headers.get("Authorization"), "Bearer TOKEN")

    def test_received_at_cache_hit(self) -> None:
        base_url = "https://graph.example/v1.0"
        start_url = (
            f"{base_url}/users/user123/mailFolders/Inbox/messages/delta"
            "?%24select=id%2CreceivedDateTime&%24top=1"
        )
        responses = {
            start_url: json.dumps(
                {"value": [{"id": "m1", "receivedDateTime": "2026-01-17T07:55:11Z"}]}
            ).encode("utf-8")
        }
        requester = _FakeRequester(responses)
        adapter = M365GraphMailIngestAdapter(
            user_id="user123",
            access_token_provider=lambda: "TOKEN",
            folder_id="Inbox",
            base_url=base_url,
            request_bytes=requester,
        )

        refs, _ = adapter.list_message_refs(cursor=None, limit=1)
        self.assertEqual([r.source_message_id for r in refs], ["m1"])
        calls_before = len(requester.calls)
        dt = adapter.get_received_at(MessageRef(source_message_id="m1"))
        self.assertEqual(dt, datetime(2026, 1, 17, 7, 55, 11, tzinfo=timezone.utc))
        self.assertEqual(len(requester.calls), calls_before)

    def test_attachment_fetch_bytes(self) -> None:
        base_url = "https://graph.example/v1.0"
        list_url = (
            f"{base_url}/users/user123/messages/m1/attachments"
            "?$select=id,name,contentType,size,@odata.type"
        )
        get_url = f"{base_url}/users/user123/messages/m1/attachments/a1"

        responses = {
            list_url: json.dumps(
                {
                    "value": [
                        {
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "id": "a1",
                            "name": "a.txt",
                            "contentType": "text/plain",
                            "size": 3,
                        }
                    ]
                }
            ).encode("utf-8"),
            get_url: json.dumps(
                {
                    "@odata.type": "#microsoft.graph.fileAttachment",
                    "contentBytes": base64.b64encode(b"abc").decode("ascii"),
                }
            ).encode("utf-8"),
        }
        requester = _FakeRequester(responses)
        adapter = M365GraphMailIngestAdapter(
            user_id="user123",
            access_token_provider=lambda: "TOKEN",
            base_url=base_url,
            request_bytes=requester,
        )

        attachments = list(adapter.list_attachments(MessageRef(source_message_id="m1")))
        self.assertEqual(len(attachments), 1)
        self.assertEqual(attachments[0].attachment_id, "m1:a1")
        raw = adapter.fetch_attachment_bytes(attachments[0])
        self.assertEqual(raw, b"abc")


if __name__ == "__main__":
    unittest.main()
