from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from ieim.case_adapter.adapter import CaseAdapter
from ieim.case_adapter.idempotency import build_idempotency_key


@dataclass(frozen=True)
class CaseStageResult:
    case_id: Optional[str]
    blocked: bool


@dataclass
class CaseStage:
    adapter: CaseAdapter

    def apply(
        self,
        *,
        normalized_message: dict,
        routing_decision: dict,
        attachments: list[dict],
        request_info_draft: Optional[str] = None,
        reply_draft: Optional[str] = None,
    ) -> CaseStageResult:
        actions = list(routing_decision.get("actions") or [])
        message_fingerprint = str(normalized_message.get("message_fingerprint") or "")
        rule_id = str(routing_decision.get("rule_id") or "")
        rule_version = str(routing_decision.get("rule_version") or "")

        if "BLOCK_CASE_CREATE" in actions:
            return CaseStageResult(case_id=None, blocked=True)

        create_case = "CREATE_CASE" in actions
        if create_case and "ADD_REQUEST_INFO_DRAFT" in actions and request_info_draft is None:
            raise ValueError("request_info_draft is required by routing action")
        if create_case and "ADD_REPLY_DRAFT" in actions and reply_draft is None:
            raise ValueError("reply_draft is required by routing action")

        case_id: Optional[str] = None
        if create_case:
            key = build_idempotency_key(
                message_fingerprint=message_fingerprint,
                rule_id=rule_id,
                rule_version=rule_version,
                operation="CREATE_CASE",
            )
            case_id = self.adapter.create_case(
                idempotency_key=key,
                queue_id=str(routing_decision.get("queue_id") or ""),
                title=str(normalized_message.get("subject") or ""),
            )

        if case_id is None:
            return CaseStageResult(case_id=None, blocked=False)

        if "ATTACH_ORIGINAL_EMAIL" in actions:
            key = build_idempotency_key(
                message_fingerprint=message_fingerprint,
                rule_id=rule_id,
                rule_version=rule_version,
                operation="ATTACH_ORIGINAL_EMAIL",
            )
            self.adapter.attach_artifact(
                idempotency_key=key,
                case_id=case_id,
                artifact={
                    "uri": str(normalized_message.get("raw_mime_uri") or ""),
                    "sha256": str(normalized_message.get("raw_mime_sha256") or ""),
                    "kind": "RAW_MIME",
                },
            )

        if "ATTACH_ALL_FILES" in actions:
            for att in attachments:
                att_id = str(att.get("attachment_id") or "")
                key = build_idempotency_key(
                    message_fingerprint=message_fingerprint,
                    rule_id=rule_id,
                    rule_version=rule_version,
                    operation=f"ATTACH:{att_id}",
                )
                self.adapter.attach_artifact(
                    idempotency_key=key,
                    case_id=case_id,
                    artifact={
                        "uri": str(att.get("extracted_text_uri") or ""),
                        "sha256": str(att.get("sha256") or ""),
                        "kind": "ATTACHMENT",
                        "attachment_id": att_id,
                    },
                )

        if "ADD_REQUEST_INFO_DRAFT" in actions:
            key = build_idempotency_key(
                message_fingerprint=message_fingerprint,
                rule_id=rule_id,
                rule_version=rule_version,
                operation="ADD_REQUEST_INFO_DRAFT",
            )
            self.adapter.add_draft_message(idempotency_key=key, case_id=case_id, draft=request_info_draft)

        if "ADD_REPLY_DRAFT" in actions:
            key = build_idempotency_key(
                message_fingerprint=message_fingerprint,
                rule_id=rule_id,
                rule_version=rule_version,
                operation="ADD_REPLY_DRAFT",
            )
            self.adapter.add_draft_message(idempotency_key=key, case_id=case_id, draft=reply_draft)

        return CaseStageResult(case_id=case_id, blocked=False)
