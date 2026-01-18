from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class CursorState:
    cursor: Optional[str]


def read_cursor(path: Path) -> CursorState:
    if not path.exists():
        return CursorState(cursor=None)
    obj = json.loads(path.read_text(encoding="utf-8"))
    cursor = obj.get("cursor")
    if cursor is not None and not isinstance(cursor, str):
        raise ValueError("cursor must be a string or null")
    return CursorState(cursor=cursor)


def write_cursor(path: Path, state: CursorState) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps({"cursor": state.cursor}, indent=2) + "\n", encoding="utf-8")
    tmp.replace(path)

