from __future__ import annotations

import html
import re
from typing import Any

from bs4 import BeautifulSoup

from app.integrations.microsoft_graph.mail_client_types import GraphMailMessage

UNKNOWN_VALUE = "-"


def parse_graph_mail_payload(payload: dict[str, Any]) -> GraphMailMessage:
    """
    Graph 응답 payload를 GraphMailMessage로 정규화한다.

    Args:
        payload: Graph 메시지 응답

    Returns:
        정규화된 메시지 모델
    """
    from_payload = payload.get("from", {})
    email_address = from_payload.get("emailAddress", {}) if isinstance(from_payload, dict) else {}
    body_payload = payload.get("body", {})
    body_content = ""
    body_content_type = ""
    if isinstance(body_payload, dict):
        body_content = str(body_payload.get("content") or "")
        body_content_type = str(body_payload.get("contentType") or "")
    body_preview = str(payload.get("bodyPreview") or "")
    body_text = extract_body_text(
        content=body_content,
        content_type=body_content_type,
        body_preview=body_preview,
    )
    return GraphMailMessage(
        message_id=str(payload.get("id") or ""),
        subject=str(payload.get("subject") or ""),
        from_address=str(email_address.get("address") or ""),
        received_date=str(payload.get("receivedDateTime") or ""),
        body_text=body_text,
        internet_message_id=str(payload.get("internetMessageId") or ""),
        web_link=str(payload.get("webLink") or ""),
    )


def extract_body_text(content: str, content_type: str, body_preview: str) -> str:
    """
    Graph body payload를 contentType 기준으로 텍스트 본문으로 정규화한다.

    Args:
        content: `body.content` 문자열
        content_type: `body.contentType` 값
        body_preview: Graph `bodyPreview` 문자열

    Returns:
        정규화된 본문 텍스트
    """
    normalized_content = str(content or "").strip()
    if not normalized_content:
        return str(body_preview or "").strip()
    if str(content_type or "").strip().lower() == "html":
        return html_to_text(content=normalized_content)
    return normalize_plain_body_text(content=normalized_content)


def html_to_text(content: str) -> str:
    """
    HTML 본문을 텍스트로 정규화한다.

    Args:
        content: HTML 원문 문자열

    Returns:
        태그 제거/공백 정리된 텍스트
    """
    soup = BeautifulSoup(str(content or ""), "html.parser")
    for removable in soup.find_all(["style", "script", "noscript"]):
        removable.decompose()
    text = soup.get_text(separator="\n")
    text = html.unescape(text)
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def normalize_plain_body_text(content: str) -> str:
    """
    text 본문을 줄바꿈/공백 기준으로 정규화한다.

    Args:
        content: text 본문 문자열

    Returns:
        정규화된 text 본문
    """
    text = str(content or "").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def extract_aadsts_metadata(error_description: str) -> dict[str, str]:
    """
    AADSTS 에러 문자열에서 추적 메타를 파싱한다.

    Args:
        error_description: MSAL 에러 설명 문자열

    Returns:
        trace/correlation/timestamp 메타 정보
    """
    trace_id_match = re.search(r"Trace ID:\s*([a-f0-9-]+)", error_description, flags=re.IGNORECASE)
    correlation_id_match = re.search(r"Correlation ID:\s*([a-f0-9-]+)", error_description, flags=re.IGNORECASE)
    timestamp_match = re.search(r"Timestamp:\s*([0-9TZ:\-\.]+)", error_description)
    return {
        "trace_id": trace_id_match.group(1) if trace_id_match else UNKNOWN_VALUE,
        "correlation_id": correlation_id_match.group(1) if correlation_id_match else UNKNOWN_VALUE,
        "timestamp": timestamp_match.group(1) if timestamp_match else UNKNOWN_VALUE,
    }
