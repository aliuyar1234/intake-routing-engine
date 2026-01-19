#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()

def _maybe_normalize_text_bytes(b: bytes) -> bytes:
    # Make MANIFEST stable across platforms with different Git line-ending behavior.
    # This is intentionally conservative: if a file looks binary (NUL byte), do not
    # rewrite bytes before hashing.
    if b"\x00" in b:
        return b
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def compute_file_hash(path: Path) -> str:
    return sha256_hex(_maybe_normalize_text_bytes(path.read_bytes()))


def parse_manifest(text: str):
    entries = {}
    for line in text.splitlines():
        line = line.strip()
        if not line:
            continue
        # sha256sum format: <hash><two spaces><path>
        if "  " not in line:
            raise ValueError(f"invalid manifest line: {line}")
        h, p = line.split("  ", 1)
        entries[p] = h
    return entries


def list_all_files():
    files = []
    excluded_top_level = {
        "audit",
        "hitl",
        "observability",
        "out",
        "raw_store",
        "state",
        ".venv",
        "venv",
        "ENV",
    }
    for p in ROOT.rglob("*"):
        if p.is_dir():
            continue
        rel = p.relative_to(ROOT)
        if rel.as_posix() == "MANIFEST.sha256":
            continue
        if rel.parts and rel.parts[0] in excluded_top_level:
            continue
        if ".git" in rel.parts or "__pycache__" in rel.parts:
            continue
        if rel.suffix == ".pyc":
            continue
        files.append(rel.as_posix())
    return sorted(files)


def main() -> int:
    if not MANIFEST.exists():
        print("MANIFEST_CHECK_FAILED: missing MANIFEST.sha256")
        return 60

    try:
        manifest_entries = parse_manifest(MANIFEST.read_text(encoding="utf-8"))
    except Exception as e:
        print(f"MANIFEST_CHECK_FAILED: {e}")
        return 60

    expected_files = list_all_files()
    missing = [f for f in expected_files if f not in manifest_entries]
    extra = [f for f in manifest_entries.keys() if f not in expected_files]

    mismatched = []
    for f in expected_files:
        path = ROOT / f
        h = compute_file_hash(path)
        if manifest_entries.get(f) != h:
            mismatched.append((f, manifest_entries.get(f), h))

    if missing or extra or mismatched:
        print("MANIFEST_CHECK_FAILED")
        if missing:
            print("MISSING_ENTRIES")
            for f in missing[:200]:
                print(f)
        if extra:
            print("EXTRA_ENTRIES")
            for f in extra[:200]:
                print(f)
        if mismatched:
            print("MISMATCHED_HASHES")
            for f, old, new in mismatched[:200]:
                print(f"{f}: manifest={old} actual={new}")
        return 60

    print("MANIFEST_CHECK_OK")
    return 0


def _self_test():
    # A minimal internal check to ensure sha256 of empty file is stable.
    assert sha256_hex(b"") == hashlib.sha256(b"").hexdigest()


if __name__ == "__main__":
    _self_test()
    sys.exit(main())
