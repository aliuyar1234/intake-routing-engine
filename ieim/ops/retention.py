from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Optional, Sequence


def _require_dict(obj: Any, *, path: str) -> dict[str, Any]:
    if not isinstance(obj, dict):
        raise ValueError(f"{path} must be an object")
    return obj


def _require_int(obj: Any, *, path: str) -> int:
    if not isinstance(obj, int):
        raise ValueError(f"{path} must be an integer")
    return int(obj)


def _require_str(obj: Any, *, path: str) -> str:
    if not isinstance(obj, str) or not obj:
        raise ValueError(f"{path} must be a non-empty string")
    return obj


def _parse_rfc3339(dt: str) -> datetime:
    if dt.endswith("Z"):
        dt = dt[:-1] + "+00:00"
    return datetime.fromisoformat(dt)


def _format_datetime(dt: datetime) -> str:
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True)
class RetentionConfig:
    raw_days: int
    normalized_days: int
    audit_years: int


def load_retention_config(*, path: Path) -> RetentionConfig:
    try:
        import yaml
    except Exception as e:
        raise RuntimeError(f"PyYAML dependency unavailable: {e}") from e

    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    doc = _require_dict(doc, path="config")
    retention = _require_dict(doc.get("retention"), path="retention")

    raw_days = _require_int(retention.get("raw_days"), path="retention.raw_days")
    normalized_days = _require_int(retention.get("normalized_days"), path="retention.normalized_days")
    audit_years = _require_int(retention.get("audit_years"), path="retention.audit_years")

    if raw_days < 0 or normalized_days < 0 or audit_years < 0:
        raise ValueError("retention values must be >= 0")

    return RetentionConfig(raw_days=raw_days, normalized_days=normalized_days, audit_years=audit_years)


@dataclass(frozen=True)
class AttachmentInfo:
    attachment_id: str
    sha256: str
    extracted_text_uri: Optional[str]
    extracted_text_sha256: Optional[str]


def _load_attachment_infos(*, attachments_dir: Path) -> dict[str, AttachmentInfo]:
    infos: dict[str, AttachmentInfo] = {}
    for p in sorted(attachments_dir.glob("*.artifact.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        att_id = str(obj.get("attachment_id") or p.stem.replace(".artifact", ""))
        sha = str(obj.get("sha256") or "")
        if not att_id or not sha:
            continue
        infos[att_id] = AttachmentInfo(
            attachment_id=att_id,
            sha256=sha,
            extracted_text_uri=obj.get("extracted_text_uri"),
            extracted_text_sha256=obj.get("extracted_text_sha256"),
        )
    return infos


@dataclass(frozen=True)
class NormalizedMessageInfo:
    message_id: str
    run_id: str
    ingested_at: datetime
    raw_mime_uri: str
    raw_mime_sha256: str
    attachment_ids: Sequence[str]


def _load_normalized_messages(*, normalized_dir: Path) -> list[NormalizedMessageInfo]:
    out: list[NormalizedMessageInfo] = []
    for p in sorted(normalized_dir.glob("*.json")):
        obj = json.loads(p.read_text(encoding="utf-8"))
        try:
            message_id = _require_str(obj.get("message_id"), path="message_id")
            run_id = _require_str(obj.get("run_id"), path="run_id")
            ingested_at = _parse_rfc3339(_require_str(obj.get("ingested_at"), path="ingested_at"))
            raw_mime_uri = _require_str(obj.get("raw_mime_uri"), path="raw_mime_uri")
            raw_mime_sha256 = _require_str(obj.get("raw_mime_sha256"), path="raw_mime_sha256")
        except Exception:
            continue

        att_ids_raw = obj.get("attachment_ids") or []
        if not isinstance(att_ids_raw, list) or not all(isinstance(x, str) for x in att_ids_raw):
            att_ids_raw = []

        out.append(
            NormalizedMessageInfo(
                message_id=message_id,
                run_id=run_id,
                ingested_at=ingested_at,
                raw_mime_uri=raw_mime_uri,
                raw_mime_sha256=raw_mime_sha256,
                attachment_ids=tuple(att_ids_raw),
            )
        )
    return out


def _safe_resolve_under(*, base_dir: Path, rel_path: str) -> Path:
    p = (base_dir / rel_path).resolve()
    base = base_dir.resolve()
    if p == base or base not in p.parents:
        raise ValueError(f"refusing to access outside base_dir: {rel_path}")
    return p


@dataclass(frozen=True)
class RetentionPlan:
    cutoff_raw: datetime
    to_delete_raw_mime_uris: Sequence[str]
    to_delete_attachment_hashes: Sequence[str]
    to_delete_extracted_text_uris: Sequence[str]


def plan_raw_retention(
    *,
    normalized_messages: list[NormalizedMessageInfo],
    attachment_infos: dict[str, AttachmentInfo],
    raw_days: int,
    now: datetime,
) -> RetentionPlan:
    cutoff = now - timedelta(days=raw_days)

    expired: list[NormalizedMessageInfo] = []
    retained: list[NormalizedMessageInfo] = []
    for nm in normalized_messages:
        if nm.ingested_at < cutoff:
            expired.append(nm)
        else:
            retained.append(nm)

    expired_raw_mime_uris = {nm.raw_mime_uri for nm in expired}
    retained_raw_mime_uris = {nm.raw_mime_uri for nm in retained}

    expired_attachment_hashes: set[str] = set()
    retained_attachment_hashes: set[str] = set()
    expired_text_uris: set[str] = set()
    retained_text_uris: set[str] = set()

    def add_from(nm: NormalizedMessageInfo, *, into_hashes: set[str], into_text_uris: set[str]) -> None:
        for att_id in nm.attachment_ids:
            info = attachment_infos.get(att_id)
            if info is None:
                continue
            if info.sha256:
                into_hashes.add(info.sha256)
            uri = info.extracted_text_uri
            if isinstance(uri, str) and uri:
                into_text_uris.add(uri)

    for nm in expired:
        add_from(nm, into_hashes=expired_attachment_hashes, into_text_uris=expired_text_uris)
    for nm in retained:
        add_from(nm, into_hashes=retained_attachment_hashes, into_text_uris=retained_text_uris)

    to_delete_raw_mime = sorted(expired_raw_mime_uris - retained_raw_mime_uris)
    to_delete_atts = sorted(expired_attachment_hashes - retained_attachment_hashes)
    to_delete_text = sorted(expired_text_uris - retained_text_uris)

    return RetentionPlan(
        cutoff_raw=cutoff,
        to_delete_raw_mime_uris=tuple(to_delete_raw_mime),
        to_delete_attachment_hashes=tuple(to_delete_atts),
        to_delete_extracted_text_uris=tuple(to_delete_text),
    )


@dataclass(frozen=True)
class RetentionReport:
    status: str
    now: str
    cutoff_raw: str
    raw_days: int
    candidates: dict[str, Any]
    applied: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "now": self.now,
            "cutoff_raw": self.cutoff_raw,
            "raw_days": self.raw_days,
            "candidates": dict(self.candidates),
            "applied": dict(self.applied),
        }


def _delete_file(path: Path, *, dry_run: bool) -> dict[str, Any]:
    if not path.exists():
        return {"path": path.as_posix(), "status": "MISSING"}
    if dry_run:
        return {"path": path.as_posix(), "status": "DRY_RUN"}
    path.unlink()
    return {"path": path.as_posix(), "status": "DELETED"}


def run_raw_retention(
    *,
    base_dir: Path,
    derived_base_dir: Optional[Path],
    normalized_dir: Path,
    attachments_dir: Path,
    raw_days: int,
    now: datetime,
    dry_run: bool,
    report_path: Optional[Path] = None,
) -> RetentionReport:
    derived_base_dir = derived_base_dir or base_dir

    nms = _load_normalized_messages(normalized_dir=normalized_dir)
    att_infos = _load_attachment_infos(attachments_dir=attachments_dir)
    plan = plan_raw_retention(
        normalized_messages=nms, attachment_infos=att_infos, raw_days=raw_days, now=now
    )

    candidates = {
        "raw_mime_uris": list(plan.to_delete_raw_mime_uris),
        "attachment_sha256": list(plan.to_delete_attachment_hashes),
        "extracted_text_uris": list(plan.to_delete_extracted_text_uris),
    }

    applied = {"raw_mime": [], "attachments": [], "extracted_text": []}

    for uri in plan.to_delete_raw_mime_uris:
        p = _safe_resolve_under(base_dir=base_dir, rel_path=uri)
        applied["raw_mime"].append(_delete_file(p, dry_run=dry_run))

    attachments_root = (base_dir / "raw_store" / "attachments").resolve()
    if attachments_root.exists():
        for sha in plan.to_delete_attachment_hashes:
            if not sha.startswith("sha256:"):
                continue
            hex_hash = sha.split(":", 1)[1]
            for p in sorted(attachments_root.glob(hex_hash + "*")):
                if p.name.endswith(".tmp"):
                    continue
                applied["attachments"].append(_delete_file(p, dry_run=dry_run))

    for uri in plan.to_delete_extracted_text_uris:
        p = _safe_resolve_under(base_dir=derived_base_dir, rel_path=uri)
        applied["extracted_text"].append(_delete_file(p, dry_run=dry_run))

    report = RetentionReport(
        status="DRY_RUN" if dry_run else "APPLIED",
        now=_format_datetime(now),
        cutoff_raw=_format_datetime(plan.cutoff_raw),
        raw_days=raw_days,
        candidates=candidates,
        applied=applied,
    )

    if report_path is not None:
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_path.write_text(json.dumps(report.to_dict(), indent=2, ensure_ascii=False, sort_keys=True) + "\n", encoding="utf-8")

    return report
