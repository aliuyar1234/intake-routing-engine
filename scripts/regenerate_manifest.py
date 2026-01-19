#!/usr/bin/env python3
import hashlib
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
MANIFEST = ROOT / "MANIFEST.sha256"


def sha256_hex(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


def _maybe_normalize_text_bytes(b: bytes) -> bytes:
    if b"\x00" in b:
        return b
    return b.replace(b"\r\n", b"\n").replace(b"\r", b"\n")


def compute_file_hash(path: Path) -> str:
    return sha256_hex(_maybe_normalize_text_bytes(path.read_bytes()))


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
    files = list_all_files()
    lines = []
    for rel in files:
        h = compute_file_hash(ROOT / rel)
        lines.append(f"{h}  {rel}")

    MANIFEST.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    print(f"MANIFEST_REGENERATED: {len(files)} entries")
    return 0


if __name__ == "__main__":
    sys.exit(main())

