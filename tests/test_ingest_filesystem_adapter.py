import hashlib
import json
import unittest
from datetime import datetime
from pathlib import Path

from ieim.ingest.filesystem_adapter import FilesystemMailIngestAdapter
from ieim.ingest.adapter import MessageRef


def _sha256_prefixed(data: bytes) -> str:
    return "sha256:" + hashlib.sha256(data).hexdigest()


def _parse_iso_z(value: str) -> datetime:
    v = value
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    return datetime.fromisoformat(v)


class TestFilesystemMailIngestAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.root = Path(__file__).resolve().parents[1]
        cls.raw_mime_dir = cls.root / "data" / "samples" / "raw_mime"
        cls.attachments_dir = cls.root / "data" / "samples" / "attachments"
        cls.emails_dir = cls.root / "data" / "samples" / "emails"
        cls.adapter = FilesystemMailIngestAdapter(
            raw_mime_dir=cls.raw_mime_dir,
            attachments_dir=cls.attachments_dir,
        )

    def test_list_message_refs_cursor_is_stable(self) -> None:
        all_ids = sorted(p.stem for p in self.raw_mime_dir.glob("*.eml"))
        cursor = None
        seen: list[str] = []
        while True:
            refs, cursor = self.adapter.list_message_refs(cursor=cursor, limit=2)
            if not refs:
                break
            seen.extend([r.source_message_id for r in refs])
        self.assertEqual(seen, all_ids)

    def test_fetch_raw_mime_hash_matches_sample_inputs(self) -> None:
        for p in sorted(self.emails_dir.glob("*.json")):
            msg = json.loads(p.read_text(encoding="utf-8"))
            msg_id = msg["message_id"]
            expected = msg["raw_mime_sha256"]
            raw = self.adapter.fetch_raw_mime(ref=MessageRef(source_message_id=msg_id))
            self.assertEqual(_sha256_prefixed(raw), expected)

    def test_received_at_matches_sample_inputs(self) -> None:
        for p in sorted(self.emails_dir.glob("*.json")):
            msg = json.loads(p.read_text(encoding="utf-8"))
            msg_id = msg["message_id"]
            expected = _parse_iso_z(msg["received_at"])
            received = self.adapter.get_received_at(ref=MessageRef(source_message_id=msg_id))
            self.assertEqual(received, expected)

    def test_attachments_mapping_and_hashes(self) -> None:
        by_message: dict[str, list[dict]] = {}
        for artifact_path in self.attachments_dir.glob("*.artifact.json"):
            artifact = json.loads(artifact_path.read_text(encoding="utf-8"))
            by_message.setdefault(artifact["message_id"], []).append(artifact)

        for message_id, artifacts in by_message.items():
            refs = self.adapter.list_attachments(ref=MessageRef(source_message_id=message_id))
            ref_ids = sorted(a.attachment_id for a in refs)
            art_ids = sorted(a["attachment_id"] for a in artifacts)
            self.assertEqual(ref_ids, art_ids)

            expected_by_id = {a["attachment_id"]: a for a in artifacts}
            for a in refs:
                raw = self.adapter.fetch_attachment_bytes(a)
                self.assertEqual(_sha256_prefixed(raw), expected_by_id[a.attachment_id]["sha256"])


if __name__ == "__main__":
    unittest.main()
