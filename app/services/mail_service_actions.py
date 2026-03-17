from __future__ import annotations

from typing import TYPE_CHECKING, Any

from app.services.mail_service_utils import build_mail_context_payload
from app.services.mail_text_utils import (
    extract_recipients_from_body,
    select_salient_summary_sentences,
    trim_sentence,
)

if TYPE_CHECKING:
    from app.services.mail_service import MailRecord


def build_current_mail_post_action_payload(mail: "MailRecord | None") -> dict[str, Any]:
    """`current_mail` 후속 액션의 완료 페이로드를 생성한다."""
    if mail is None:
        return {"action": "current_mail", "status": "failed", "reason": "현재 메일을 찾지 못했습니다."}
    return {
        "action": "current_mail",
        "status": "completed",
        "message_id": mail.message_id,
        "subject": mail.subject,
        "from_address": mail.from_address,
        "received_date": mail.received_date,
        "body_preview": mail.body_text[:400],
        "mail_context": build_mail_context_payload(mail=mail),
    }


def build_context_only_post_action_payload(action: str, mail: "MailRecord | None") -> dict[str, Any]:
    """메일 후속 액션 요청에 대한 context-only 페이로드를 생성한다."""
    return {
        "action": action or "summary",
        "status": "context_only",
        "mail_context": build_mail_context_payload(mail=mail),
    }


def extract_key_facts_from_mail(mail: "MailRecord | None", limit: int = 5) -> list[str]:
    """현재 메일에서 핵심 포인트를 추출한다."""
    if mail is None:
        return ["현재 메일이 없습니다."]
    fact_lines = select_salient_summary_sentences(text=mail.body_text, line_target=max(1, limit * 2))
    if not fact_lines:
        return ["핵심 추출 대상 본문이 없습니다."]
    markers = ("요청", "일정", "회의", "마감", "필요", "확인", "공유", "중요")
    prioritized = [item for item in fact_lines if any(mark in item for mark in markers)]
    base = prioritized or fact_lines
    return [trim_sentence(sentence=item) for item in base[: max(1, limit)]]


def extract_recipients_from_mail(mail: "MailRecord | None", limit: int = 10) -> list[str]:
    """현재 메일 본문 헤더(`To:`) 기준으로 수신자 목록을 추출한다."""
    if mail is None:
        return ["현재 메일이 없습니다."]
    recipients = extract_recipients_from_body(text=mail.body_text)
    if not recipients:
        return ["수신자 정보를 본문에서 찾지 못했습니다."]
    return recipients[: max(1, limit)]
