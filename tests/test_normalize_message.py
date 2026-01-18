import json
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

import jsonschema

from ieim.normalize.normalized_message import build_normalized_message
from ieim.raw_store import FileRawStore


def _parse_iso_z(value: str) -> datetime:
    v = value
    if v.endswith("Z"):
        v = v[:-1] + "+00:00"
    return datetime.fromisoformat(v)


class TestNormalization(unittest.TestCase):
    def test_build_normalized_message_validates_against_schema(self) -> None:
        root = Path(__file__).resolve().parents[1]
        raw_mime_path = root / "data" / "samples" / "raw_mime" / "101f1b6d-ea7b-54b4-833d-53e11c190174.eml"
        sample_nm_path = root / "data" / "samples" / "emails" / "101f1b6d-ea7b-54b4-833d-53e11c190174.json"
        schema_path = root / "schemas" / "normalized_message.schema.json"

        raw = raw_mime_path.read_bytes()
        sample = json.loads(sample_nm_path.read_text(encoding="utf-8"))

        with tempfile.TemporaryDirectory() as td:
            store = FileRawStore(base_dir=Path(td))
            put = store.put_bytes(kind="mime", data=raw, file_extension=".eml")

            nm = build_normalized_message(
                raw_mime=raw,
                message_id=sample["message_id"],
                run_id=sample["run_id"],
                ingested_at=_parse_iso_z(sample["ingested_at"]),
                received_at=_parse_iso_z(sample["received_at"]),
                ingestion_source=sample["ingestion_source"],
                raw_mime_uri=put.uri,
                raw_mime_sha256=put.sha256,
                attachment_ids=[],
            )

        schema = json.loads(schema_path.read_text(encoding="utf-8"))
        jsonschema.Draft202012Validator(schema).validate(nm)

        self.assertEqual(nm["raw_mime_sha256"], put.sha256)
        self.assertEqual(nm["subject_c14n"], nm["subject"].lower())
        self.assertEqual(nm["body_text_c14n"], nm["body_text"].lower())


if __name__ == "__main__":
    unittest.main()
