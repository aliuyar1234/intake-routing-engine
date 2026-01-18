from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class HealthReport:
    status: str
    details: dict[str, Any]


def ok(*, component: str) -> HealthReport:
    return HealthReport(status="OK", details={"component": component})

