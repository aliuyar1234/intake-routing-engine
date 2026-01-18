from __future__ import annotations

import shutil
import subprocess
import tempfile
from abc import ABC, abstractmethod
from dataclasses import dataclass
from pathlib import Path
from typing import Optional


@dataclass(frozen=True)
class OCRResult:
    text: str
    confidence: float


class OCRProcessor(ABC):
    @abstractmethod
    def ocr(self, *, data: bytes, filename: str, mime_type: str) -> Optional[OCRResult]:
        """Return extracted text and confidence (0..1) if OCR succeeds."""


class TesseractOCRProcessor(OCRProcessor):
    def __init__(self, *, tesseract_path: Optional[str] = None, lang: str = "eng") -> None:
        self._tesseract_path = tesseract_path or shutil.which("tesseract")
        self._lang = lang

    def ocr(self, *, data: bytes, filename: str, mime_type: str) -> Optional[OCRResult]:
        if not self._tesseract_path:
            return None
        if not mime_type.startswith("image/"):
            return None

        ext = Path(filename).suffix or ".img"
        with tempfile.TemporaryDirectory() as td:
            img = Path(td) / f"input{ext}"
            img.write_bytes(data)

            try:
                txt = subprocess.run(
                    [self._tesseract_path, str(img), "stdout", "-l", self._lang],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                if txt.returncode != 0:
                    return None
                text = txt.stdout.strip()
                if not text:
                    return OCRResult(text="", confidence=0.0)

                tsv = subprocess.run(
                    [self._tesseract_path, str(img), "stdout", "-l", self._lang, "tsv"],
                    capture_output=True,
                    text=True,
                    timeout=120,
                )
                confs: list[float] = []
                if tsv.returncode == 0:
                    lines = [ln for ln in tsv.stdout.splitlines() if ln.strip()]
                    if lines:
                        header = lines[0].split("\t")
                        if "conf" in header:
                            idx = header.index("conf")
                            for ln in lines[1:]:
                                parts = ln.split("\t")
                                if len(parts) <= idx:
                                    continue
                                try:
                                    c = float(parts[idx])
                                except ValueError:
                                    continue
                                if c >= 0:
                                    confs.append(c)
                confidence = (sum(confs) / len(confs)) / 100.0 if confs else 0.5
                confidence = max(0.0, min(1.0, confidence))
                return OCRResult(text=text, confidence=confidence)
            except Exception:
                return None

