from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ieim.config import IEIMConfig
from ieim.raw_store import sha256_prefixed


@lru_cache(maxsize=1)
def _extraction_schema_id_and_version() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas" / "extraction_result.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str) or not schema_id:
        raise ValueError("extraction_result.schema.json missing $id")
    version = schema_id.rsplit(":", 1)[-1]
    return schema_id, version


def _snippet_sha256(snippet: str) -> str:
    return sha256_prefixed(snippet.encode("utf-8"))


def _sha256_value(value: str) -> str:
    return sha256_prefixed(value.encode("utf-8"))


def _provenance(*, source: str, start: int, end: int, snippet: str) -> dict:
    return {
        "source": source,
        "start": int(start),
        "end": int(end),
        "snippet_redacted": snippet,
        "snippet_sha256": _snippet_sha256(snippet),
    }


_POLICY_NUMBER_RE = re.compile(r"\b(?P<num>\d{2}-\d{7})\b")
_CLAIM_NUMBER_RE = re.compile(r"\b(?P<clm>clm-\d{4}-\d{4})\b")
_DATE_RE = re.compile(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b")
_LOC_ORt_RE = re.compile(r"\bort:\s+(?P<loc>[a-zäöüß-]{2,})\b")
_LOC_IN_RE = re.compile(r"\bin\s+(?P<loc>[a-zäöüß-]{2,})\b")
_IBAN_RE = re.compile(r"\b(?P<iban>[A-Z]{2}\d{2}[A-Z0-9]{10,30})\b", re.IGNORECASE)


def _find_first_regex(text: str, regex: re.Pattern) -> Optional[re.Match]:
    return regex.search(text)


def _iban_redact(value: str) -> str:
    v = value.strip()
    if len(v) <= 8:
        return v
    return v[:4].lower() + "…" + v[-4:].lower()


@dataclass
class DeterministicExtractor:
    config: IEIMConfig

    def extract(self, *, normalized_message: dict, attachments: list[dict]) -> dict:
        schema_id, schema_version = _extraction_schema_id_and_version()

        message_id = str(normalized_message["message_id"])
        run_id = str(normalized_message["run_id"])
        created_at = str(normalized_message["ingested_at"])

        subject_c14n = str(normalized_message.get("subject_c14n") or "")
        body_c14n = str(normalized_message.get("body_text_c14n") or "")

        entities: list[dict] = []

        policy_match = _find_first_regex(body_c14n, _POLICY_NUMBER_RE) or _find_first_regex(
            subject_c14n, _POLICY_NUMBER_RE
        )
        if policy_match is not None:
            number = policy_match.group("num")
            source = "BODY_C14N" if policy_match.re is _POLICY_NUMBER_RE and policy_match.string is body_c14n else "SUBJECT_C14N"
            entities.append(
                {
                    "entity_type": "ENT_POLICY_NUMBER",
                    "value": number,
                    "value_redacted": number,
                    "value_sha256": _sha256_value(number),
                    "store_mode": "FULL",
                    "confidence": 0.95,
                    "provenance": _provenance(
                        source=source,
                        start=policy_match.start("num"),
                        end=policy_match.end("num"),
                        snippet=number,
                    ),
                }
            )

        claim_match = _find_first_regex(subject_c14n, _CLAIM_NUMBER_RE) or _find_first_regex(
            body_c14n, _CLAIM_NUMBER_RE
        )
        if claim_match is not None:
            raw = claim_match.group("clm")
            value = raw.upper()
            source = "SUBJECT_C14N" if claim_match.string is subject_c14n else "BODY_C14N"
            entities.append(
                {
                    "entity_type": "ENT_CLAIM_NUMBER",
                    "value": value,
                    "value_redacted": value,
                    "value_sha256": _sha256_value(value),
                    "store_mode": "FULL",
                    "confidence": 0.95,
                    "provenance": _provenance(
                        source=source,
                        start=claim_match.start("clm"),
                        end=claim_match.end("clm"),
                        snippet=raw,
                    ),
                }
            )

        date_match = _find_first_regex(body_c14n, _DATE_RE)
        if date_match is not None:
            dt = date_match.group("date")
            entities.append(
                {
                    "entity_type": "ENT_DATE",
                    "value": dt,
                    "value_redacted": dt,
                    "value_sha256": _sha256_value(dt),
                    "store_mode": "FULL",
                    "confidence": 0.9,
                    "provenance": _provenance(
                        source="BODY_C14N",
                        start=date_match.start("date"),
                        end=date_match.end("date"),
                        snippet=dt,
                    ),
                }
            )

        loc_match = _find_first_regex(body_c14n, _LOC_ORt_RE)
        if loc_match is not None:
            loc = loc_match.group("loc")
            snippet = f"ort: {loc}"
            start = loc_match.start(0)
            end = loc_match.end(0)
            entities.append(
                {
                    "entity_type": "ENT_LOCATION",
                    "value": loc.capitalize(),
                    "value_redacted": loc.capitalize(),
                    "value_sha256": _sha256_value(loc.capitalize()),
                    "store_mode": "FULL",
                    "confidence": 0.8,
                    "provenance": _provenance(source="BODY_C14N", start=start, end=end, snippet=snippet),
                }
            )
        else:
            loc_match = _find_first_regex(body_c14n, _LOC_IN_RE)
            if loc_match is not None:
                loc = loc_match.group("loc")
                entities.append(
                    {
                        "entity_type": "ENT_LOCATION",
                        "value": loc.capitalize(),
                        "value_redacted": loc.capitalize(),
                        "value_sha256": _sha256_value(loc.capitalize()),
                        "store_mode": "FULL",
                        "confidence": 0.8,
                        "provenance": _provenance(
                            source="BODY_C14N",
                            start=loc_match.start("loc"),
                            end=loc_match.end("loc"),
                            snippet=loc,
                        ),
                    }
                )

        if self.config.extraction.iban_policy.enabled:
            iban_match = _IBAN_RE.search(body_c14n)
            if iban_match is not None:
                raw = iban_match.group("iban")
                normalized = raw.upper()
                entities.append(
                    {
                        "entity_type": "ENT_IBAN",
                        "value": None if self.config.extraction.iban_policy.store_mode == "HASH_ONLY" else normalized,
                        "value_redacted": _iban_redact(normalized),
                        "value_sha256": _sha256_value(normalized),
                        "store_mode": self.config.extraction.iban_policy.store_mode,
                        "confidence": 0.85,
                        "provenance": _provenance(
                            source="BODY_C14N",
                            start=iban_match.start("iban"),
                            end=iban_match.end("iban"),
                            snippet=raw.lower(),
                        ),
                    }
                )

        if all(str(a.get("av_status") or "") == "CLEAN" for a in attachments):
            for att in attachments:
                for cand in att.get("doc_type_candidates") or []:
                    label = cand.get("doc_type_label")
                    if label != "DOC_PHOTO_EVIDENCE":
                        continue
                    evidence = (cand.get("evidence") or [])
                    if not evidence:
                        continue
                    ev0 = evidence[0]
                    snippet = str(ev0.get("snippet_redacted") or "")
                    entities.append(
                        {
                            "entity_type": "ENT_DOCUMENT_TYPE",
                            "value": label,
                            "value_redacted": label,
                            "value_sha256": _sha256_value(label),
                            "store_mode": "FULL",
                            "confidence": float(cand.get("confidence") or 0.0),
                            "provenance": _provenance(
                                source="ATTACHMENT_TEXT",
                                start=int(ev0.get("start") or 0),
                                end=int(ev0.get("end") or 0),
                                snippet=snippet,
                            ),
                        }
                    )
                    break

        return {
            "schema_id": schema_id,
            "schema_version": schema_version,
            "message_id": message_id,
            "run_id": run_id,
            "entities": entities,
            "created_at": created_at,
        }

