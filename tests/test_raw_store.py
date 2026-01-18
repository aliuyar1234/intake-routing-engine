import tempfile
import unittest
from pathlib import Path

from ieim.raw_store import FileRawStore, sha256_prefixed


class TestFileRawStore(unittest.TestCase):
    def test_put_bytes_is_content_addressed_and_append_only(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = FileRawStore(base_dir=base)

            data = b"abc"
            r1 = store.put_bytes(kind="mime", data=data, file_extension=".eml")
            r2 = store.put_bytes(kind="mime", data=data, file_extension=".eml")

            self.assertEqual(r1.sha256, sha256_prefixed(data))
            self.assertEqual(r1.uri, r2.uri)
            self.assertEqual(store.get_bytes(uri=r1.uri), data)

    def test_put_bytes_detects_immutability_violation(self) -> None:
        with tempfile.TemporaryDirectory() as td:
            base = Path(td)
            store = FileRawStore(base_dir=base)

            data = b"abc"
            r = store.put_bytes(kind="mime", data=data, file_extension=".eml")
            path = (base / r.uri).resolve()

            path.write_bytes(b"def")
            with self.assertRaises(RuntimeError):
                store.put_bytes(kind="mime", data=data, file_extension=".eml")


if __name__ == "__main__":
    unittest.main()

