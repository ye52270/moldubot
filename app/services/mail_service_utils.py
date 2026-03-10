from __future__ import annotations

from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from app.services.mail_service import MailRecord


def build_mail_record_from_row(row: dict[str, Any]) -> "MailRecord":
    """
    DB 조회 행(dict)을 `MailRecord`로 변환한다.

    Args:
        row: DB 조회 결과 사전

    Returns:
        변환된 메일 레코드
    """
    from app.services.mail_service import MailRecord

    return MailRecord(
        message_id=str(row.get("message_id") or ""),
        subject=str(row.get("subject") or ""),
        from_address=str(row.get("from_address") or ""),
        received_date=str(row.get("received_date") or ""),
        body_text=str(row.get("body_text") or ""),
        code_body_text=str(row.get("code_body_text") or ""),
        body_full_text=str(row.get("body_full_text") or ""),
        summary_text=str(row.get("summary_text") or ""),
        web_link=str(row.get("web_link") or ""),
    )


def build_mail_context_payload(mail: "MailRecord | None") -> dict[str, Any]:
    """
    LLM 요약 품질 보강용 메일 컨텍스트 페이로드를 생성한다.

    Args:
        mail: 기준 메일 레코드

    Returns:
        제목/발신자/수신시각/요약텍스트/본문 발췌를 포함한 사전
    """
    if mail is None:
        return {}
    from app.services.mail_text_utils import build_mail_route_compact_text, extract_sender_display_name

    return {
        "message_id": mail.message_id,
        "subject": mail.subject,
        "from_address": mail.from_address,
        "from_display_name": extract_sender_display_name(mail.from_address),
        "received_date": mail.received_date,
        "web_link": mail.web_link,
        "summary_text": mail.summary_text,
        "body_excerpt": build_body_excerpt(text=mail.body_text),
        "body_code_excerpt": build_body_excerpt(text=mail.code_body_text or mail.body_text),
        "route_flow": build_mail_route_compact_text(text=mail.body_text),
    }


def build_body_excerpt(text: str, max_chars: int = 2400) -> str:
    """
    LLM 근거 확보용 본문 발췌를 생성한다.

    Args:
        text: 원본 본문 텍스트
        max_chars: 최대 길이

    Returns:
        정규화된 본문 발췌 문자열
    """
    normalized = str(text or "").replace("\r", "\n")
    lines = [line.strip() for line in normalized.split("\n") if line and line.strip()]
    compact = "\n".join(lines)
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "\n...(truncated)"


def build_upsert_update_query(include_web_link: bool, include_summary: bool) -> str:
    """
    web_link 컬럼 포함 여부에 따라 UPDATE SQL을 생성한다.

    Args:
        include_web_link: web_link 컬럼 포함 여부
        include_summary: summary 컬럼 포함 여부

    Returns:
        UPDATE SQL 문자열
    """
    if include_web_link and include_summary:
        return (
            "UPDATE emails SET "
            "subject = ?, from_address = ?, received_date = ?, body_preview = ?, body_full = ?, body_clean = ?, summary = ?, web_link = ? "
            "WHERE message_id = ?"
        )
    if include_summary:
        return (
            "UPDATE emails SET "
            "subject = ?, from_address = ?, received_date = ?, body_preview = ?, body_full = ?, body_clean = ?, summary = ? "
            "WHERE message_id = ?"
        )
    if include_web_link:
        return (
            "UPDATE emails SET "
            "subject = ?, from_address = ?, received_date = ?, body_preview = ?, body_full = ?, body_clean = ?, web_link = ? "
            "WHERE message_id = ?"
        )
    return (
        "UPDATE emails SET "
        "subject = ?, from_address = ?, received_date = ?, body_preview = ?, body_full = ?, body_clean = ? "
        "WHERE message_id = ?"
    )


def build_upsert_insert_query(include_web_link: bool, include_summary: bool) -> str:
    """
    web_link 컬럼 포함 여부에 따라 INSERT SQL을 생성한다.

    Args:
        include_web_link: web_link 컬럼 포함 여부
        include_summary: summary 컬럼 포함 여부

    Returns:
        INSERT SQL 문자열
    """
    if include_web_link and include_summary:
        return (
            "INSERT INTO emails (message_id, subject, from_address, received_date, body_preview, body_full, body_clean, summary, web_link) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
        )
    if include_summary:
        return (
            "INSERT INTO emails (message_id, subject, from_address, received_date, body_preview, body_full, body_clean, summary) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
    if include_web_link:
        return (
            "INSERT INTO emails (message_id, subject, from_address, received_date, body_preview, body_full, body_clean, web_link) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)"
        )
    return (
        "INSERT INTO emails (message_id, subject, from_address, received_date, body_preview, body_full, body_clean) "
        "VALUES (?, ?, ?, ?, ?, ?, ?)"
    )
