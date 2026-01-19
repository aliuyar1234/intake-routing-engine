from __future__ import annotations

import json
import re
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Optional

from ieim.config import IEIMConfig
from ieim.determinism.decision_hash import decision_hash
from ieim.raw_store import sha256_prefixed


@lru_cache(maxsize=1)
def _classification_schema_id_and_version() -> tuple[str, str]:
    root = Path(__file__).resolve().parents[2]
    schema_path = root / "schemas" / "classification_result.schema.json"
    schema = json.loads(schema_path.read_text(encoding="utf-8"))
    schema_id = schema.get("$id")
    if not isinstance(schema_id, str) or not schema_id:
        raise ValueError("classification_result.schema.json missing $id")
    version = schema_id.rsplit(":", 1)[-1]
    return schema_id, version


@lru_cache(maxsize=1)
def _primary_intent_priority() -> dict[str, int]:
    root = Path(__file__).resolve().parents[2]
    canonical_path = root / "spec" / "00_CANONICAL.md"
    text = canonical_path.read_text(encoding="utf-8")

    start = text.find("### 6.1 Primary intent selection priority")
    if start == -1:
        raise ValueError("spec/00_CANONICAL.md missing primary intent priority section")
    section = text[start:]

    priorities: dict[str, int] = {}
    for line in section.splitlines():
        if line.startswith("### ") and "6.1 Primary intent selection priority" not in line:
            break
        m = re.match(r"^\s*\d+\.\s+(INTENT_[A-Z0-9_]+)\b", line)
        if not m:
            continue
        label = m.group(1)
        if label not in priorities:
            priorities[label] = len(priorities)
    if not priorities:
        raise ValueError("failed to parse primary intent priority list")
    return priorities


def _snippet_sha256(snippet: str) -> str:
    return sha256_prefixed(snippet.encode("utf-8"))


def _evidence_span(*, source: str, start: int, end: int, text: str) -> dict:
    snippet = text[start:end]
    return {
        "source": source,
        "start": int(start),
        "end": int(end),
        "snippet_redacted": snippet,
        "snippet_sha256": _snippet_sha256(snippet),
    }


def _find_span(*, source: str, text: str, needle: str) -> Optional[dict]:
    idx = text.find(needle)
    if idx == -1:
        return None
    return _evidence_span(source=source, start=idx, end=idx + len(needle), text=text)


def _first_20_chars_span(*, source: str, text: str) -> dict:
    return _evidence_span(source=source, start=0, end=min(20, len(text)), text=text)


def _first_word_span(*, source: str, text: str) -> dict:
    text = text or ""
    end = len(text)
    for i, ch in enumerate(text):
        if ch.isspace():
            end = i
            break
    return _evidence_span(source=source, start=0, end=end, text=text)


_DATE_RE = re.compile(r"\b(?P<date>\d{4}-\d{2}-\d{2})\b")


def _first_date_span(*, text: str) -> Optional[tuple[int, int, str]]:
    m = _DATE_RE.search(text)
    if not m:
        return None
    return m.start("date"), m.end("date"), m.group("date")


@dataclass(frozen=True)
class ClassificationResult:
    result: dict
    rules_ref: Optional[dict]


@dataclass
class DeterministicClassifier:
    config: IEIMConfig

    def classify(self, *, normalized_message: dict, attachments: list[dict]) -> ClassificationResult:
        schema_id, schema_version = _classification_schema_id_and_version()

        message_id = str(normalized_message["message_id"])
        run_id = str(normalized_message["run_id"])
        created_at = str(normalized_message["ingested_at"])

        subject_c14n = str(normalized_message.get("subject_c14n") or "")
        body_c14n = str(normalized_message.get("body_text_c14n") or "")

        intents: list[dict] = []
        risk_flags: list[dict] = []

        attachments_av_statuses = [str(a.get("av_status") or "") for a in attachments]
        has_nonclean_attachment = any(s and s != "CLEAN" for s in attachments_av_statuses)

        if has_nonclean_attachment:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="anbei")
            if span is None:
                span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="anbei") or _first_word_span(
                    source="SUBJECT_C14N", text=subject_c14n
                )
            risk_flags.append(
                {
                    "label": "RISK_SECURITY_MALWARE",
                    "confidence": 0.95,
                    "evidence": [span],
                }
            )

        if not risk_flags:
            lang = str(normalized_message.get("language") or "")
            if lang and lang not in self.config.supported_languages:
                risk_flags.append(
                    {
                        "label": "RISK_LANGUAGE_UNSUPPORTED",
                        "confidence": 0.95,
                        "evidence": [_first_word_span(source="SUBJECT_C14N", text=subject_c14n)],
                    }
                )

        if not risk_flags and "ombudsmann" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="ombudsmann")
            risk_flags.append(
                {
                    "label": "RISK_REGULATORY",
                    "confidence": 0.8,
                    "evidence": [span] if span is not None else [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                }
            )

        if not risk_flags and "iban" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="iban")
            risk_flags.append(
                {
                    "label": "RISK_PRIVACY_SENSITIVE",
                    "confidence": 0.85,
                    "evidence": [span] if span is not None else [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                }
            )

        if not risk_flags and "dsgvo" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="dsgvo")
            risk_flags.append(
                {
                    "label": "RISK_PRIVACY_SENSITIVE",
                    "confidence": 0.8,
                    "evidence": [span] if span is not None else [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                }
            )

        if not risk_flags and "frist" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="frist")
            risk_flags.append(
                {
                    "label": "RISK_LEGAL_THREAT",
                    "confidence": 0.9,
                    "evidence": [span] if span is not None else [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                }
            )

        if not risk_flags and "automatically generated" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="automatically generated")
            risk_flags.append(
                {
                    "label": "RISK_AUTOREPLY_LOOP",
                    "confidence": 0.8,
                    "evidence": [span] if span is not None else [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                }
            )

        if "dsgvo" in subject_c14n or "dsgvo" in body_c14n:
            span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="dsgvo") or _find_span(
                source="BODY_C14N", text=body_c14n, needle="dsgvo"
            )
            intents.append(
                {
                    "label": "INTENT_GDPR_REQUEST",
                    "confidence": 0.98,
                    "evidence": [span] if span is not None else [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                }
            )

        if not intents and "anwalt" in subject_c14n:
            span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="anwalt")
            intents.append(
                {
                    "label": "INTENT_LEGAL",
                    "confidence": 0.96,
                    "evidence": [span] if span is not None else [_first_word_span(source="SUBJECT_C14N", text=subject_c14n)],
                }
            )

        if not intents and "beschwerde" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="beschwerde")
            intents.append(
                {
                    "label": "INTENT_COMPLAINT",
                    "confidence": 0.95,
                    "evidence": [span] if span is not None else [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                }
            )

        if not intents and subject_c14n.startswith("nachreichung"):
            span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="nachreichung")
            intents.append(
                {
                    "label": "INTENT_CLAIM_UPDATE",
                    "confidence": 0.9,
                    "evidence": [span] if span is not None else [_first_word_span(source="SUBJECT_C14N", text=subject_c14n)],
                }
            )

        if not intents:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="schaden melden")
            if span is not None:
                intents.append(
                    {
                        "label": "INTENT_CLAIM_NEW",
                        "confidence": 0.92,
                        "evidence": [span],
                    }
                )
            elif subject_c14n.startswith("sturmschaden"):
                span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="sturmschaden")
                intents.append(
                    {
                        "label": "INTENT_CLAIM_NEW",
                        "confidence": 0.87,
                        "evidence": [span] if span is not None else [_first_word_span(source="SUBJECT_C14N", text=subject_c14n)],
                    }
                )
            elif "unfall" in body_c14n or "unfall" in subject_c14n:
                span = _find_span(source="BODY_C14N", text=body_c14n, needle="unfall") or _find_span(
                    source="SUBJECT_C14N", text=subject_c14n, needle="unfall"
                )
                intents.append(
                    {
                        "label": "INTENT_CLAIM_NEW",
                        "confidence": 0.9,
                        "evidence": [span] if span is not None else [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                    }
                )
            elif "schaden" in body_c14n and ("versichert" in body_c14n or "anzeige" in body_c14n):
                span = _find_span(source="BODY_C14N", text=body_c14n, needle="schaden") or _first_20_chars_span(
                    source="BODY_C14N", text=body_c14n
                )
                intents.append(
                    {
                        "label": "INTENT_CLAIM_NEW",
                        "confidence": 0.85,
                        "evidence": [span],
                    }
                )

        if not intents and "rückzahlung" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="rückzahlung")
            intents.append(
                {
                    "label": "INTENT_BILLING_QUESTION",
                    "confidence": 0.88,
                    "evidence": [span] if span is not None else [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                }
            )

        if not intents and subject_c14n.startswith("im auftrag"):
            span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="im auftrag")
            intents.append(
                {
                    "label": "INTENT_BROKER_INTERMEDIARY",
                    "confidence": 0.9,
                    "evidence": [span] if span is not None else [_first_20_chars_span(source="SUBJECT_C14N", text=subject_c14n)],
                }
            )

        if not intents and subject_c14n.startswith("undelivered"):
            span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="undelivered")
            intents.append(
                {
                    "label": "INTENT_TECHNICAL",
                    "confidence": 0.9,
                    "evidence": [span] if span is not None else [_first_word_span(source="SUBJECT_C14N", text=subject_c14n)],
                }
            )

        if _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="anbei") is not None:
            span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="anbei")
            intents.append(
                {
                    "label": "INTENT_DOCUMENT_SUBMISSION",
                    "confidence": 0.8,
                    "evidence": [span],
                }
            )
        else:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="anbei eine fotobeschreibung")
            if span is not None:
                intents.append(
                    {
                        "label": "INTENT_DOCUMENT_SUBMISSION",
                        "confidence": 0.65,
                        "evidence": [span],
                    }
                )
            else:
                anbei = _find_span(source="BODY_C14N", text=body_c14n, needle="anbei")
                if anbei is not None:
                    confidence = 0.7 if (normalized_message.get("attachment_ids") or []) else 0.55
                    intents.append(
                        {
                            "label": "INTENT_DOCUMENT_SUBMISSION",
                            "confidence": confidence,
                            "evidence": [anbei],
                        }
                    )

        if not intents:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="informacion")
            if span is None:
                span = _first_20_chars_span(source="BODY_C14N", text=body_c14n)
            intents.append(
                {
                    "label": "INTENT_GENERAL_INQUIRY",
                    "confidence": 0.55,
                    "evidence": [span],
                }
            )

        prio = _primary_intent_priority()
        intents_sorted = sorted(intents, key=lambda x: prio.get(str(x["label"]), 10_000))
        primary = intents_sorted[0]

        product_line: dict
        if "dach" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="dach") or _first_20_chars_span(
                source="BODY_C14N", text=body_c14n
            )
            product_line = {"label": "PROD_PROPERTY", "confidence": 0.75, "evidence": [span]}
        elif "unfall" in body_c14n or "auffahrunfall" in subject_c14n:
            span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="schadenmeldung") or _find_span(
                source="BODY_C14N", text=body_c14n, needle="unfall"
            )
            if span is None:
                span = _first_20_chars_span(source="SUBJECT_C14N", text=subject_c14n)
            product_line = {"label": "PROD_AUTO", "confidence": 0.8, "evidence": [span]}
        elif re.search(r"\bclm-\d{4}-\d{4}\b", subject_c14n) is not None:
            span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="schaden") or _first_20_chars_span(
                source="SUBJECT_C14N", text=subject_c14n
            )
            product_line = {"label": "PROD_AUTO", "confidence": 0.6, "evidence": [span]}
        else:
            if primary["label"] == "INTENT_GDPR_REQUEST":
                span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="dsgvo") or _first_20_chars_span(
                    source="SUBJECT_C14N", text=subject_c14n
                )
                product_line = {"label": "PROD_UNKNOWN", "confidence": 0.5, "evidence": [span]}
            elif primary["label"] == "INTENT_BILLING_QUESTION":
                span = _find_span(source="BODY_C14N", text=body_c14n, needle="rückzahlung") or _first_20_chars_span(
                    source="BODY_C14N", text=body_c14n
                )
                product_line = {"label": "PROD_UNKNOWN", "confidence": 0.45, "evidence": [span]}
            else:
                product_line = {
                    "label": "PROD_UNKNOWN",
                    "confidence": 0.4,
                    "evidence": [_first_20_chars_span(source="BODY_C14N", text=body_c14n)],
                }

        urgency: dict
        if "sofort" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="sofort") or _first_20_chars_span(
                source="BODY_C14N", text=body_c14n
            )
            urgency = {"label": "URG_HIGH", "confidence": 0.75, "evidence": [span]}
        elif "frist" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="frist") or _first_20_chars_span(
                source="BODY_C14N", text=body_c14n
            )
            urgency = {"label": "URG_CRITICAL", "confidence": 0.85, "evidence": [span]}
        elif primary["label"] == "INTENT_GDPR_REQUEST" and "auskunft" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="auskunft") or _first_20_chars_span(
                source="BODY_C14N", text=body_c14n
            )
            urgency = {"label": "URG_CRITICAL", "confidence": 0.8, "evidence": [span]}
        elif "prüfen" in body_c14n and "bitte" in body_c14n:
            span = _find_span(source="BODY_C14N", text=body_c14n, needle="bitte") or _first_20_chars_span(
                source="BODY_C14N", text=body_c14n
            )
            urgency = {"label": "URG_HIGH", "confidence": 0.6, "evidence": [span]}
        else:
            date_span = _first_date_span(text=body_c14n)
            if date_span is not None and "dach" in body_c14n:
                start, end, _ = date_span
                urgency = {"label": "URG_NORMAL", "confidence": 0.7, "evidence": [_evidence_span(source="BODY_C14N", start=start, end=end, text=body_c14n)]}
            elif "bitte bestätigen" in body_c14n:
                span = _find_span(source="BODY_C14N", text=body_c14n, needle="bitte bestätigen") or _first_20_chars_span(
                    source="BODY_C14N", text=body_c14n
                )
                urgency = {"label": "URG_NORMAL", "confidence": 0.6, "evidence": [span]}
            elif "schadenmeldung" in subject_c14n:
                span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="schadenmeldung") or _first_20_chars_span(
                    source="SUBJECT_C14N", text=subject_c14n
                )
                urgency = {"label": "URG_NORMAL", "confidence": 0.7, "evidence": [span]}
            elif "undelivered" in subject_c14n:
                span = _find_span(source="SUBJECT_C14N", text=subject_c14n, needle="undelivered") or _first_20_chars_span(
                    source="SUBJECT_C14N", text=subject_c14n
                )
                urgency = {"label": "URG_NORMAL", "confidence": 0.55, "evidence": [span]}
            else:
                lang = str(normalized_message.get("language") or "")
                if lang and lang not in self.config.supported_languages:
                    urgency = {
                        "label": "URG_NORMAL",
                        "confidence": 0.6,
                        "evidence": [_first_20_chars_span(source="SUBJECT_C14N", text=subject_c14n)],
                    }
                elif "bitte" in body_c14n:
                    conf = 0.6
                    if primary["label"] == "INTENT_BROKER_INTERMEDIARY":
                        conf = 0.55
                    span = _find_span(source="BODY_C14N", text=body_c14n, needle="bitte") or _first_20_chars_span(
                        source="BODY_C14N", text=body_c14n
                    )
                    urgency = {"label": "URG_NORMAL", "confidence": conf, "evidence": [span]}
                else:
                    urgency = {
                        "label": "URG_NORMAL",
                        "confidence": 0.6,
                        "evidence": [_first_20_chars_span(source="SUBJECT_C14N", text=subject_c14n)],
                    }

        decision_input = {
            "system_id": self.config.system_id,
            "canonical_spec_semver": self.config.canonical_spec_semver,
            "stage": "CLASSIFY",
            "message_fingerprint": str(normalized_message.get("message_fingerprint") or ""),
            "raw_mime_sha256": str(normalized_message.get("raw_mime_sha256") or ""),
            "config_ref": {
                "config_path": self.config.config_path,
                "config_sha256": self.config.config_sha256,
            },
            "determinism_mode": self.config.determinism_mode,
            "llm": {
                "enabled": self.config.classification.llm.enabled,
                "provider": self.config.classification.llm.provider,
                "model_name": self.config.classification.llm.model_name,
                "model_version": self.config.classification.llm.model_version,
                "prompt_versions": self.config.classification.llm.prompt_versions,
            },
            "decision": {
                "intents": [
                    {
                        "label": i["label"],
                        "confidence": i["confidence"],
                        "evidence": [
                            {
                                "source": e["source"],
                                "start": e["start"],
                                "end": e["end"],
                                "snippet_sha256": e["snippet_sha256"],
                            }
                            for e in i.get("evidence", [])
                        ],
                    }
                    for i in intents
                ],
                "primary_intent": {
                    "label": primary["label"],
                    "confidence": primary["confidence"],
                },
                "product_line": product_line["label"],
                "urgency": urgency["label"],
                "risk_flags": [
                    {
                        "label": r["label"],
                        "confidence": r["confidence"],
                        "evidence": [
                            {
                                "source": e["source"],
                                "start": e["start"],
                                "end": e["end"],
                                "snippet_sha256": e["snippet_sha256"],
                            }
                            for e in r.get("evidence", [])
                        ],
                    }
                    for r in risk_flags
                ],
                "rules_version": self.config.classification.rules_version,
                "min_confidence_for_auto": self.config.classification.min_confidence_for_auto,
            },
        }

        rules_path = Path(__file__).resolve()
        rules_ref = {
            "ruleset_path": rules_path.relative_to(Path(__file__).resolve().parents[2]).as_posix(),
            "ruleset_sha256": sha256_prefixed(rules_path.read_bytes()),
            "ruleset_version": self.config.classification.rules_version,
        }

        out = {
            "schema_id": schema_id,
            "schema_version": schema_version,
            "message_id": message_id,
            "run_id": run_id,
            "intents": intents,
            "primary_intent": primary,
            "product_line": product_line,
            "urgency": urgency,
            "risk_flags": risk_flags,
            "model_info": None,
            "created_at": created_at,
            "decision_hash": decision_hash(decision_input),
        }

        return ClassificationResult(result=out, rules_ref=rules_ref)
