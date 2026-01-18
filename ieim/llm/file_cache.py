from __future__ import annotations

import json
import os
import tempfile
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ieim.determinism.jcs import jcs_bytes
from ieim.raw_store import sha256_prefixed


def _rfc3339_now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def default_llm_cache_dir() -> Path:
    env = os.getenv("IEIM_LLM_CACHE_DIR")
    if env:
        return Path(env)
    return Path(tempfile.gettempdir()) / "ieim_llm_cache"


@dataclass(frozen=True)
class LLMCacheKey:
    stage: str
    provider: str
    model_name: str
    model_version: str
    prompt_version: str
    prompt_sha256: str
    message_fingerprint: str

    def stable_id(self) -> str:
        obj = {
            "message_fingerprint": self.message_fingerprint,
            "model_name": self.model_name,
            "model_version": self.model_version,
            "prompt_sha256": self.prompt_sha256,
            "prompt_version": self.prompt_version,
            "provider": self.provider,
            "stage": self.stage,
        }
        return sha256_prefixed(jcs_bytes(obj))


@dataclass(frozen=True)
class LLMCacheEntry:
    key: LLMCacheKey
    response: dict[str, Any]
    stored_at: str


class FileLLMCache:
    def __init__(self, *, base_dir: Optional[Path] = None) -> None:
        self._base_dir = (base_dir or default_llm_cache_dir()).resolve()
        self._base_dir.mkdir(parents=True, exist_ok=True)

    def _path_for(self, key: LLMCacheKey) -> Path:
        hex_hash = key.stable_id().split(":", 1)[1]
        return self._base_dir / "cache" / key.provider / key.stage / f"{hex_hash}.json"

    def get(self, key: LLMCacheKey) -> Optional[LLMCacheEntry]:
        path = self._path_for(key)
        if not path.exists():
            return None
        obj = json.loads(path.read_text(encoding="utf-8"))
        response = obj.get("response")
        if not isinstance(response, dict):
            return None
        stored_at = obj.get("stored_at")
        if not isinstance(stored_at, str) or not stored_at:
            stored_at = "unknown"
        return LLMCacheEntry(key=key, response=response, stored_at=stored_at)

    def put(self, *, key: LLMCacheKey, response: dict[str, Any]) -> Path:
        path = self._path_for(key)
        path.parent.mkdir(parents=True, exist_ok=True)

        if path.exists():
            existing = json.loads(path.read_text(encoding="utf-8"))
            if existing.get("response") != response:
                raise RuntimeError(f"LLM cache immutability violation: {path}")
            return path

        obj = {"key": key.__dict__, "response": response, "stored_at": _rfc3339_now()}
        data = (json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")

        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(path)
        return path


class DailyCallCounter:
    def __init__(self, *, base_dir: Optional[Path] = None) -> None:
        self._base_dir = (base_dir or default_llm_cache_dir()).resolve()
        self._path = self._base_dir / "usage" / "daily_calls.json"
        self._path.parent.mkdir(parents=True, exist_ok=True)

    def _today(self) -> str:
        return datetime.now(timezone.utc).date().isoformat()

    def _load(self) -> dict[str, Any]:
        if not self._path.exists():
            return {"by_date": {}}
        try:
            obj = json.loads(self._path.read_text(encoding="utf-8"))
        except Exception:
            return {"by_date": {}}
        if not isinstance(obj, dict) or "by_date" not in obj:
            return {"by_date": {}}
        if not isinstance(obj.get("by_date"), dict):
            return {"by_date": {}}
        return obj

    def _store(self, obj: dict[str, Any]) -> None:
        data = (json.dumps(obj, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8")
        tmp = self._path.with_suffix(self._path.suffix + ".tmp")
        tmp.write_bytes(data)
        tmp.replace(self._path)

    def can_consume(self, *, max_calls_per_day: int) -> bool:
        if max_calls_per_day <= 0:
            return False
        obj = self._load()
        by_date = obj["by_date"]
        today = self._today()
        current = int(by_date.get(today) or 0)
        return current < max_calls_per_day

    def consume(self) -> None:
        obj = self._load()
        by_date = obj["by_date"]
        today = self._today()
        by_date[today] = int(by_date.get(today) or 0) + 1
        self._store(obj)
