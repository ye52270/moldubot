from __future__ import annotations

from typing import Any

from app.services.search_chat_stakeholders import build_stakeholders
from app.services.tech_issue_cluster_service import build_tech_issue_clusters


def build_context_enrichment(
    answer: str,
    answer_format: dict[str, Any],
    tool_payload: dict[str, Any],
    evidence_mails: list[dict[str, str]],
    next_actions: list[dict[str, str]],
    llm_recipient_roles: list[dict[str, str]] | None = None,
    llm_recipient_todos: list[dict[str, str]] | None = None,
) -> dict[str, Any]:
    """
    컨텍스트 탭 강화를 위한 요약 메타데이터를 구성한다.
    """
    source_text = _resolve_mail_source_text(tool_payload=tool_payload)
    reply_alert = _build_reply_alert(answer=answer, next_actions=next_actions)
    timeline = _build_thread_timeline(tool_payload=tool_payload, evidence_mails=evidence_mails)
    stakeholders = build_stakeholders(
        answer_format=answer_format,
        source_text=source_text,
        tool_payload=tool_payload,
        evidence_mails=evidence_mails,
        llm_recipient_roles=llm_recipient_roles,
        llm_recipient_todos=llm_recipient_todos,
    )
    tech_issue_clusters = build_tech_issue_clusters(
        tool_payload=tool_payload,
        evidence_mails=evidence_mails,
    )
    return {
        "reply_alert": reply_alert,
        "thread_timeline": timeline,
        "stakeholders": stakeholders,
        "tech_issue_clusters": tech_issue_clusters,
    }


def _resolve_mail_source_text(tool_payload: dict[str, Any]) -> str:
    if not isinstance(tool_payload, dict):
        return ""
    context = tool_payload.get("mail_context")
    if not isinstance(context, dict):
        return ""
    parts = [
        str(context.get("summary_text") or "").strip(),
        str(context.get("body_excerpt") or "").strip(),
        str(context.get("body_preview") or "").strip(),
    ]
    return "\n".join([part for part in parts if part])


def _build_reply_alert(answer: str, next_actions: list[dict[str, str]]) -> dict[str, str]:
    action_title = ""
    for item in next_actions[:3]:
        if not isinstance(item, dict):
            continue
        title = str(item.get("title") or "").strip()
        query = str(item.get("query") or "").strip()
        merged = f"{title} {query}".lower()
        if "회신" in merged or "답장" in merged or "reply" in merged:
            action_title = title or query
            break
    normalized_answer = str(answer or "").lower()
    required = bool(action_title) or ("회신" in normalized_answer) or ("답장" in normalized_answer)
    if not required:
        return {"required": False, "title": "", "description": "", "severity": "none"}
    description = action_title or "회신 필요 항목이 감지되었습니다."
    return {"required": True, "title": "회신 필요", "description": description, "severity": "medium"}


def _build_thread_timeline(
    tool_payload: dict[str, Any],
    evidence_mails: list[dict[str, str]],
) -> list[dict[str, str]]:
    context = tool_payload.get("mail_context") if isinstance(tool_payload, dict) else {}
    context = context if isinstance(context, dict) else {}
    timeline: list[dict[str, str]] = []
    sender = str(context.get("from_display_name") or context.get("from_address") or "").strip()
    received = str(context.get("received_date") or "").strip()
    if sender or received:
        timeline.append({"actor": sender or "현재 메일", "timestamp": received, "label": "현재 메일", "state": "latest"})
    for item in evidence_mails[:3]:
        if not isinstance(item, dict):
            continue
        actor = str(item.get("sender_names") or "").strip()
        timestamp = str(item.get("received_date") or "").strip()
        subject = str(item.get("subject") or "").strip()
        if not actor and not timestamp and not subject:
            continue
        timeline.append({"actor": actor or "관련 메일", "timestamp": timestamp, "label": subject or "근거 메일", "state": "reference"})
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in timeline:
        key = "|".join([item.get("actor", ""), item.get("timestamp", ""), item.get("label", "")])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:3]
