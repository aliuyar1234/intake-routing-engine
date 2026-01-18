from __future__ import annotations

from pathlib import Path


def load_request_info_template(*, root_dir: Path, language: str) -> str:
    if language == "de":
        path = root_dir / "configs" / "templates" / "request_info_de.md"
    else:
        path = root_dir / "configs" / "templates" / "request_info_en.md"
    return path.read_text(encoding="utf-8")


def render_request_info_draft(*, template: str) -> str:
    return template

