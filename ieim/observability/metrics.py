from __future__ import annotations

import threading
from dataclasses import dataclass


try:
    from prometheus_client import CONTENT_TYPE_LATEST, Counter, Gauge, Histogram, generate_latest
except Exception as e:  # pragma: no cover
    raise RuntimeError("prometheus_client is required (requirements/runtime.txt)") from e


@dataclass
class _RatesState:
    lock: threading.Lock
    processed_total: int
    hitl_total: int


_rates = _RatesState(lock=threading.Lock(), processed_total=0, hitl_total=0)


emails_ingested_total = Counter(
    "emails_ingested_total",
    "Total emails ingested (normalized messages created).",
)

emails_processed_total = Counter(
    "emails_processed_total",
    "Total emails processed (routing decision completed).",
)

stage_events_total = Counter(
    "stage_events_total",
    "Pipeline stage completion events by stage and status.",
    labelnames=("stage", "status"),
)

hitl_items_total = Counter(
    "hitl_items_total",
    "Total HITL review items created.",
)

stage_latency_ms = Histogram(
    "stage_latency_ms",
    "Pipeline stage latency in milliseconds.",
    labelnames=("stage", "status"),
    buckets=(
        10,
        25,
        50,
        100,
        250,
        500,
        1000,
        2000,
        5000,
        10000,
        30000,
        60000,
    ),
)

hitl_rate_percent = Gauge(
    "hitl_rate_percent",
    "Percentage of processed emails routed to HITL (process-local approximation).",
)

mis_association_rate = Gauge(
    "mis_association_rate",
    "Manual identity corrections / total (process-local; reference runtime default is 0).",
)

misroute_rate = Gauge(
    "misroute_rate",
    "Manual routing corrections / total (process-local; reference runtime default is 0).",
)

ocr_error_rate = Gauge(
    "ocr_error_rate",
    "OCR errors / OCR attempts (process-local; reference runtime default is 0).",
)

llm_cost_per_email = Gauge(
    "llm_cost_per_email",
    "Estimated LLM cost per processed email (process-local; reference runtime default is 0).",
)


def observe_stage(*, stage: str, duration_ms: int, status: str) -> None:
    if duration_ms < 0:
        return
    stage_events_total.labels(stage=stage, status=status).inc()
    stage_latency_ms.labels(stage=stage, status=status).observe(duration_ms)


def inc_ingested(*, count: int = 1) -> None:
    if count <= 0:
        return
    emails_ingested_total.inc(count)


def inc_processed(*, count: int = 1) -> None:
    if count <= 0:
        return
    emails_processed_total.inc(count)
    with _rates.lock:
        _rates.processed_total += count
        if _rates.processed_total > 0:
            hitl_rate_percent.set((_rates.hitl_total / _rates.processed_total) * 100.0)


def inc_hitl(*, count: int = 1) -> None:
    if count <= 0:
        return
    hitl_items_total.inc(count)
    with _rates.lock:
        _rates.hitl_total += count
        if _rates.processed_total > 0:
            hitl_rate_percent.set((_rates.hitl_total / _rates.processed_total) * 100.0)


def render_prometheus() -> tuple[bytes, str]:
    return generate_latest(), CONTENT_TYPE_LATEST
