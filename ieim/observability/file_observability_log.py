from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

from ieim.observability.tracing import current_trace_ids

def _format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class ObservabilityEvent:
    event_type: str
    stage: str
    message_id: str
    run_id: str
    occurred_at: str
    duration_ms: Optional[int]
    status: str
    trace_id: str
    span_id: str
    fields: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "stage": self.stage,
            "message_id": self.message_id,
            "run_id": self.run_id,
            "occurred_at": self.occurred_at,
            "duration_ms": self.duration_ms,
            "status": self.status,
            "trace_id": self.trace_id,
            "span_id": self.span_id,
            "fields": dict(self.fields),
        }


def build_observability_event(
    *,
    event_type: str,
    stage: str,
    message_id: str,
    run_id: str,
    occurred_at: datetime,
    duration_ms: Optional[int],
    status: str,
    trace_id: Optional[str] = None,
    span_id: Optional[str] = None,
    fields: Optional[dict[str, Any]] = None,
) -> ObservabilityEvent:
    ids = current_trace_ids()
    trace_id = trace_id or (ids.trace_id_hex if ids is not None else None) or run_id
    span_id = span_id or (ids.span_id_hex if ids is not None else None) or f"{stage}:{event_type}"
    return ObservabilityEvent(
        event_type=event_type,
        stage=stage,
        message_id=message_id,
        run_id=run_id,
        occurred_at=_format_datetime(occurred_at),
        duration_ms=duration_ms,
        status=status,
        trace_id=trace_id,
        span_id=span_id,
        fields=fields or {},
    )


class FileObservabilityLogger:
    """Append-only observability events per (message_id, run_id)."""

    def __init__(self, *, base_dir: Path) -> None:
        self._base_dir = base_dir

    def _path_for(self, *, message_id: str, run_id: str) -> Path:
        return self._base_dir / "observability" / message_id / f"{run_id}.jsonl"

    def append(self, event: ObservabilityEvent) -> None:
        path = self._path_for(message_id=event.message_id, run_id=event.run_id)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(event.to_dict(), ensure_ascii=False) + "\n")
