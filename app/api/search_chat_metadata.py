from __future__ import annotations

import json
import re
from typing import Any

from app.api.search_chat_metadata_context import build_context_enrichment
from app.api.search_chat_metadata_evidence import build_major_point_evidence
from app.services.mail_text_utils import extract_sender_display_name

EVIDENCE_SNIPPET_MAX_CHARS = 220
EVIDENCE_MAILS_TOP_K = 5
EVIDENCE_SNIPPET_FALLBACK_KEYS: tuple[str, ...] = ("snippet", "summary_text", "body_excerpt", "body_preview")


def build_evidence_mail_item(
    message_id: str,
    subject: str,
    received_date: str,
    from_address: str,
    web_link: str,
    snippet: str = "",
) -> dict[str, str]:
    """
    채팅 응답 메타데이터용 근거메일 항목을 구성한다.
    """
    sender_name = extract_sender_display_name(from_address=from_address)
    return {
        "message_id": str(message_id or "").strip(),
        "subject": str(subject or "").strip() or "제목 없음",
        "received_date": str(received_date or "").strip() or "-",
        "sender_names": sender_name,
        "web_link": str(web_link or "").strip(),
        "snippet": str(snippet or "").strip(),
    }


def read_agent_tool_payload(agent: Any) -> dict[str, Any]:
    """agent 인스턴스에서 마지막 tool payload를 읽는다."""
    getter = getattr(agent, "get_last_tool_payload", None)
    if not callable(getter):
        return {}
    payload = getter()
    return payload if isinstance(payload, dict) else {}


def read_agent_final_answer(agent: Any) -> str:
    """agent 인스턴스에서 마지막 assistant 최종 답변을 읽는다."""
    getter = getattr(agent, "get_last_assistant_answer", None)
    if not callable(getter):
        return ""
    answer = getter()
    if not isinstance(answer, str):
        return ""
    return answer.strip()


def read_agent_raw_model_output(agent: Any) -> str:
    """agent 인스턴스에서 마지막 모델 직출력(raw)을 읽는다."""
    getter = getattr(agent, "get_last_raw_model_output", None)
    if not callable(getter):
        return ""
    output = getter()
    if not isinstance(output, str):
        return ""
    return output.strip()


def read_agent_raw_model_content(agent: Any) -> str:
    """agent 인스턴스에서 마지막 모델 content 원본 스냅샷을 문자열로 읽는다."""
    getter = getattr(agent, "get_last_raw_model_content", None)
    if not callable(getter):
        return ""
    content = getter()
    if isinstance(content, str):
        return content.strip()
    try:
        return json.dumps(content, ensure_ascii=False, indent=2)
    except (TypeError, ValueError):
        return str(content or "").strip()


def extract_tool_action(tool_payload: dict[str, Any]) -> str:
    """tool payload에서 action 문자열을 소문자로 정규화해 반환한다."""
    if not isinstance(tool_payload, dict):
        return ""
    return str(tool_payload.get("action") or "").strip().lower()


def extract_evidence_from_tool_payload(tool_payload: dict[str, Any]) -> list[dict[str, str]]:
    """
    tool payload에서 근거메일 목록을 추출한다.
    """
    if not tool_payload:
        return []
    action = extract_tool_action(tool_payload=tool_payload)
    if action != "mail_search":
        return []
    results = tool_payload.get("results")
    if not isinstance(results, list):
        return []
    evidence: list[dict[str, str]] = []
    for item in results[:EVIDENCE_MAILS_TOP_K]:
        if not isinstance(item, dict):
            continue
        evidence.append(
            {
                "message_id": str(item.get("message_id") or "").strip(),
                "subject": str(item.get("subject") or "").strip() or "제목 없음",
                "received_date": str(item.get("received_date") or "").strip() or "-",
                "sender_names": str(item.get("sender_names") or "-").strip() or "-",
                "web_link": str(item.get("web_link") or "").strip(),
                "snippet": _extract_evidence_snippet(item=item),
            }
        )
    return evidence


def _extract_evidence_snippet(item: dict[str, Any]) -> str:
    """mail_search 결과 항목에서 근거 스니펫을 우선순위 기반으로 추출한다."""
    for key in EVIDENCE_SNIPPET_FALLBACK_KEYS:
        value = str(item.get(key) or "").strip()
        if value:
            compact = re.sub(r"\s+", " ", value).strip()
            return compact[:EVIDENCE_SNIPPET_MAX_CHARS]
    return ""


def extract_aggregated_summary_from_tool_payload(tool_payload: dict[str, Any]) -> list[str]:
    """
    tool payload에서 통합 요약 라인을 추출한다.
    """
    if not tool_payload:
        return []
    action = extract_tool_action(tool_payload=tool_payload)
    if action != "mail_search":
        return []
    lines = tool_payload.get("aggregated_summary")
    if not isinstance(lines, list):
        return []
    normalized: list[str] = []
    for item in lines:
        text = str(item or "").strip()
        if text:
            normalized.append(text)
    return normalized[:5]


__all__ = [
    "build_evidence_mail_item",
    "read_agent_tool_payload",
    "read_agent_final_answer",
    "read_agent_raw_model_output",
    "read_agent_raw_model_content",
    "extract_tool_action",
    "extract_evidence_from_tool_payload",
    "extract_aggregated_summary_from_tool_payload",
    "build_context_enrichment",
    "build_major_point_evidence",
]
