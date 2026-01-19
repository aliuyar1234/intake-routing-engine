from __future__ import annotations

import hashlib
from contextlib import contextmanager
from dataclasses import dataclass
from typing import Any, Iterator, Mapping, MutableMapping, Optional


try:
    from opentelemetry import propagate, trace
    from opentelemetry.propagators.textmap import Getter, Setter
    from opentelemetry.sdk.resources import Resource
    from opentelemetry.sdk.trace import TracerProvider
    from opentelemetry.trace import Span, SpanContext, SpanKind, TraceFlags, TraceState
    from opentelemetry.trace import NonRecordingSpan
except Exception as e:  # pragma: no cover
    raise RuntimeError("opentelemetry-sdk is required (requirements/runtime.txt)") from e


_initialized = False
_enabled = False


def _stable_trace_id_from_key(key: str) -> int:
    h = hashlib.sha256(key.encode("utf-8")).digest()
    trace_id = int.from_bytes(h[:16], byteorder="big", signed=False)
    return trace_id if trace_id != 0 else 1


def _stable_span_id_from_key(key: str) -> int:
    h = hashlib.sha256(key.encode("utf-8")).digest()
    span_id = int.from_bytes(h[:8], byteorder="big", signed=False)
    return span_id if span_id != 0 else 1


class _DictGetter(Getter[Mapping[str, str]]):
    def get(self, carrier: Mapping[str, str], key: str) -> list[str]:
        if not carrier or not key:
            return []
        key_l = key.lower()
        for k, v in carrier.items():
            if str(k).lower() == key_l:
                return [str(v)]
        return []

    def keys(self, carrier: Mapping[str, str]) -> list[str]:
        return list(carrier.keys())


class _DictSetter(Setter[MutableMapping[str, str]]):
    def set(self, carrier: MutableMapping[str, str], key: str, value: str) -> None:
        carrier[key] = value


@dataclass(frozen=True)
class TraceIds:
    trace_id_hex: str
    span_id_hex: str


def init_tracing(*, enabled: bool, service_name: str) -> None:
    global _initialized, _enabled
    if _initialized and (_enabled or not enabled):
        return

    _initialized = True
    if not enabled:
        _enabled = False
        return

    provider = TracerProvider(resource=Resource.create({"service.name": service_name}))
    trace.set_tracer_provider(provider)
    _enabled = True


def extract_context_from_headers(headers: Mapping[str, str]) -> Any:
    return propagate.extract(headers, getter=_DictGetter())


def inject_context_into_headers(headers: MutableMapping[str, str]) -> None:
    propagate.inject(headers, setter=_DictSetter())


def context_for_run_id(*, run_id: str) -> Any:
    trace_id = _stable_trace_id_from_key(f"ieim:run:{run_id}")
    span_id = _stable_span_id_from_key(f"ieim:run_span:{run_id}")
    sc = SpanContext(
        trace_id=trace_id,
        span_id=span_id,
        is_remote=True,
        trace_flags=TraceFlags(TraceFlags.SAMPLED),
        trace_state=TraceState(),
    )
    return trace.set_span_in_context(NonRecordingSpan(sc))


def current_trace_ids() -> Optional[TraceIds]:
    span = trace.get_current_span()
    if span is None:
        return None
    ctx = span.get_span_context()
    if ctx is None or not ctx.is_valid:
        return None
    return TraceIds(trace_id_hex=f"{int(ctx.trace_id):032x}", span_id_hex=f"{int(ctx.span_id):016x}")


@contextmanager
def start_span(
    name: str,
    *,
    context: Any = None,
    kind: SpanKind = SpanKind.INTERNAL,
    attributes: Optional[Mapping[str, Any]] = None,
) -> Iterator[Span]:
    tracer = trace.get_tracer("ieim")
    with tracer.start_as_current_span(name, context=context, kind=kind) as span:
        if attributes:
            for k, v in attributes.items():
                try:
                    span.set_attribute(str(k), v)
                except Exception:
                    continue
        yield span


def annotate_current_span_http_status(*, status_code: int) -> None:
    span = trace.get_current_span()
    if span is None:
        return
    try:
        span.set_attribute("http.status_code", int(status_code))
    except Exception:
        return


def reset_tracing_for_tests() -> None:
    global _initialized, _enabled
    _initialized = False
    _enabled = False
