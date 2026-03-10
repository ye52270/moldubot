from __future__ import annotations

import json
import re
from typing import Any

from app.services.mail_text_utils import extract_sender_display_name
from app.services.search_chat_stakeholders import build_stakeholders
from app.services.tech_issue_cluster_service import build_tech_issue_clusters
from app.services.text_overlap_utils import (
    extract_overlap_tokens,
    normalize_compare_text,
    token_overlap_score,
)

EVIDENCE_SNIPPET_MAX_CHARS = 220
EVIDENCE_MAILS_TOP_K = 5
EVIDENCE_SNIPPET_FALLBACK_KEYS: tuple[str, ...] = (
    "snippet",
    "summary_text",
    "body_excerpt",
    "body_preview",
)


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

    Args:
        message_id: 메시지 식별자
        subject: 메일 제목
        received_date: 수신 일시
        from_address: 발신자 원문
        web_link: Outlook Web 링크
        snippet: 근거 요약/본문 스니펫

    Returns:
        근거메일 메타데이터 사전
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
    """
    agent 인스턴스에서 마지막 tool payload를 읽는다.

    Args:
        agent: deep agent 인스턴스

    Returns:
        마지막 tool payload. 없으면 빈 dict
    """
    getter = getattr(agent, "get_last_tool_payload", None)
    if not callable(getter):
        return {}
    payload = getter()
    return payload if isinstance(payload, dict) else {}


def read_agent_final_answer(agent: Any) -> str:
    """
    agent 인스턴스에서 마지막 assistant 최종 답변을 읽는다.

    Args:
        agent: deep agent 인스턴스

    Returns:
        마지막 assistant 답변 문자열. 없으면 빈 문자열
    """
    getter = getattr(agent, "get_last_assistant_answer", None)
    if not callable(getter):
        return ""
    answer = getter()
    if not isinstance(answer, str):
        return ""
    return answer.strip()


def read_agent_raw_model_output(agent: Any) -> str:
    """
    agent 인스턴스에서 마지막 모델 직출력(raw)을 읽는다.

    Args:
        agent: deep agent 인스턴스

    Returns:
        마지막 모델 직출력 문자열. 없으면 빈 문자열
    """
    getter = getattr(agent, "get_last_raw_model_output", None)
    if not callable(getter):
        return ""
    output = getter()
    if not isinstance(output, str):
        return ""
    return output.strip()


def read_agent_raw_model_content(agent: Any) -> str:
    """
    agent 인스턴스에서 마지막 모델 content 원본 스냅샷을 문자열로 읽는다.

    Args:
        agent: deep agent 인스턴스

    Returns:
        직렬화된 content 스냅샷 문자열. 없으면 빈 문자열
    """
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
    """
    tool payload에서 action 문자열을 소문자로 정규화해 반환한다.

    Args:
        tool_payload: 마지막 tool payload

    Returns:
        소문자 action 문자열. 없으면 빈 문자열
    """
    if not isinstance(tool_payload, dict):
        return ""
    return str(tool_payload.get("action") or "").strip().lower()


def extract_evidence_from_tool_payload(tool_payload: dict[str, Any]) -> list[dict[str, str]]:
    """
    tool payload에서 근거메일 목록을 추출한다.

    Args:
        tool_payload: 마지막 tool payload

    Returns:
        UI 노출용 근거메일 목록
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
    """
    mail_search 결과 항목에서 근거 스니펫을 우선순위 기반으로 추출한다.

    Args:
        item: mail_search 결과 항목

    Returns:
        정규화/길이 제한이 적용된 스니펫 문자열
    """
    for key in EVIDENCE_SNIPPET_FALLBACK_KEYS:
        value = str(item.get(key) or "").strip()
        if value:
            compact = re.sub(r"\s+", " ", value).strip()
            return compact[:EVIDENCE_SNIPPET_MAX_CHARS]
    return ""


def extract_aggregated_summary_from_tool_payload(tool_payload: dict[str, Any]) -> list[str]:
    """
    tool payload에서 통합 요약 라인을 추출한다.

    Args:
        tool_payload: 마지막 tool payload

    Returns:
        통합 요약 라인 목록
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


def build_major_point_evidence(
    answer_format: dict[str, Any],
    tool_payload: dict[str, Any],
    evidence_mails: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    주요 내용 항목별 근거(메일 문구/단락, 기술 웹출처)를 구성한다.

    Args:
        answer_format: answer_format metadata
        tool_payload: 마지막 tool payload
        evidence_mails: UI용 근거메일 목록

    Returns:
        주요 내용별 근거 목록
    """
    major_points = _extract_major_points_from_answer_format(answer_format=answer_format)
    if not major_points:
        return []
    source_text = _resolve_mail_source_text(tool_payload=tool_payload)
    sentence_candidates = _split_sentences(text=source_text)
    paragraph_candidates = _split_paragraphs(text=source_text)
    normalized_items: list[dict[str, Any]] = []
    for point in major_points[:6]:
        quote, location = _find_best_mail_evidence(
            point=point,
            sentence_candidates=sentence_candidates,
            paragraph_candidates=paragraph_candidates,
        )
        point_evidence: dict[str, Any] = {
            "point": point,
            "mail_quote": quote,
            "mail_location": location,
            "mail_subject": str(evidence_mails[0].get("subject") or "").strip() if evidence_mails else "",
            "related_mails": [],
        }
        normalized_items.append(point_evidence)
    return normalized_items

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

    Args:
        answer: 최종 응답 텍스트
        answer_format: answer_format metadata
        tool_payload: 마지막 tool payload
        evidence_mails: 근거메일 목록
        next_actions: 추천 액션 목록
        llm_recipient_roles: LLM `recipient_roles` 직렬화 목록
        llm_recipient_todos: LLM `recipient_todos` 직렬화 목록

    Returns:
        reply_alert/thread_timeline/stakeholders를 포함한 컨텍스트 메타데이터
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

def _extract_major_points_from_answer_format(answer_format: dict[str, Any]) -> list[str]:
    """
    answer_format 블록에서 `주요 내용` ordered list 항목을 추출한다.

    Args:
        answer_format: answer_format metadata

    Returns:
        주요 내용 라인 목록
    """
    if not isinstance(answer_format, dict):
        return []
    blocks = answer_format.get("blocks")
    if not isinstance(blocks, list):
        return []
    collecting = False
    lines: list[str] = []
    for block in blocks:
        if not isinstance(block, dict):
            continue
        block_type = str(block.get("type") or "").strip()
        if block_type == "heading":
            heading = normalize_compare_text(text=str(block.get("text") or ""))
            collecting = "주요내용" in heading
            continue
        if not collecting:
            continue
        if block_type not in {"ordered_list", "unordered_list"}:
            continue
        items = block.get("items")
        if not isinstance(items, list):
            continue
        for item in items:
            text = str(item or "").strip()
            if text:
                lines.append(text)
    return lines


def _resolve_mail_source_text(tool_payload: dict[str, Any]) -> str:
    """
    tool payload에서 근거 문장 탐색용 메일 원문 텍스트를 구성한다.

    Args:
        tool_payload: 마지막 tool payload

    Returns:
        문장 탐색용 텍스트
    """
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
    return _clean_mail_text(text="\n".join([part for part in parts if part]))


def _clean_mail_text(text: str) -> str:
    """
    메일 텍스트에서 HTML/노이즈를 제거한다.

    Args:
        text: 원문 텍스트

    Returns:
        정리된 텍스트
    """
    cleaned = str(text or "")
    cleaned = re.sub(r"<[^>]+>", " ", cleaned)
    cleaned = cleaned.replace("&nbsp;", " ")
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _split_sentences(text: str) -> list[str]:
    """
    텍스트를 문장 단위 후보로 분리한다.

    Args:
        text: 원문 텍스트

    Returns:
        문장 후보 목록
    """
    source = str(text or "").strip()
    if not source:
        return []
    fragments = re.split(r"(?<=[.!?。])\s+|(?<=다)\.\s+|;\s+", source)
    sentences = [str(item or "").strip() for item in fragments if str(item or "").strip()]
    return [item for item in sentences if len(item) >= 12][:80]


def _split_paragraphs(text: str) -> list[str]:
    """
    텍스트를 단락 후보로 분리한다.

    Args:
        text: 원문 텍스트

    Returns:
        단락 후보 목록
    """
    source = str(text or "").strip()
    if not source:
        return []
    raw_parts = re.split(r"\n{2,}|(?<=\.)\s{2,}", source)
    parts = [str(item or "").strip() for item in raw_parts if str(item or "").strip()]
    return [item for item in parts if len(item) >= 24][:40]


def _find_best_mail_evidence(
    point: str,
    sentence_candidates: list[str],
    paragraph_candidates: list[str],
) -> tuple[str, str]:
    """
    주요 내용과 가장 유사한 메일 문구와 단락 위치를 찾는다.

    Args:
        point: 주요 내용 문장
        sentence_candidates: 문장 후보 목록
        paragraph_candidates: 단락 후보 목록

    Returns:
        (근거 문구, 근거 단락 라벨)
    """
    point_tokens = set(extract_overlap_tokens(text=point))
    if not point_tokens:
        return "", ""
    best_sentence = ""
    best_score = 0.0
    for sentence in sentence_candidates:
        score = token_overlap_score(point_tokens=point_tokens, candidate=sentence)
        if score > best_score:
            best_sentence = sentence
            best_score = score
    if best_score < 0.12 and sentence_candidates:
        best_sentence = sentence_candidates[0]
    location = _resolve_paragraph_location(sentence=best_sentence, paragraphs=paragraph_candidates)
    return best_sentence[:180], location


def _resolve_paragraph_location(sentence: str, paragraphs: list[str]) -> str:
    """
    문장이 포함된 단락 라벨을 반환한다.

    Args:
        sentence: 근거 문장
        paragraphs: 단락 목록

    Returns:
        단락 라벨
    """
    target = str(sentence or "").strip()
    if not target:
        return ""
    for index, paragraph in enumerate(paragraphs, start=1):
        if target in paragraph:
            return f"본문 {index}단락"
    return "본문 근거 문장"


def _build_reply_alert(answer: str, next_actions: list[dict[str, str]]) -> dict[str, str]:
    """
    응답/추천액션에서 회신 필요 경고 카드를 구성한다.

    Args:
        answer: 최종 응답 텍스트
        next_actions: 추천 액션 목록

    Returns:
        회신 경고 메타데이터
    """
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
        return {
            "required": False,
            "title": "",
            "description": "",
            "severity": "none",
        }
    description = action_title or "회신 필요 항목이 감지되었습니다."
    return {
        "required": True,
        "title": "회신 필요",
        "description": description,
        "severity": "medium",
    }


def _build_thread_timeline(
    tool_payload: dict[str, Any],
    evidence_mails: list[dict[str, str]],
) -> list[dict[str, str]]:
    """
    근거메일/메일컨텍스트 기반 스레드 타임라인 항목을 생성한다.

    Args:
        tool_payload: 마지막 tool payload
        evidence_mails: 근거메일 목록

    Returns:
        최대 3건 타임라인 항목
    """
    context = tool_payload.get("mail_context") if isinstance(tool_payload, dict) else {}
    context = context if isinstance(context, dict) else {}
    timeline: list[dict[str, str]] = []
    sender = str(context.get("from_display_name") or context.get("from_address") or "").strip()
    received = str(context.get("received_date") or "").strip()
    if sender or received:
        timeline.append(
            {
                "actor": sender or "현재 메일",
                "timestamp": received,
                "label": "현재 메일",
                "state": "latest",
            }
        )
    for item in evidence_mails[:3]:
        if not isinstance(item, dict):
            continue
        actor = str(item.get("sender_names") or "").strip()
        timestamp = str(item.get("received_date") or "").strip()
        subject = str(item.get("subject") or "").strip()
        if not actor and not timestamp and not subject:
            continue
        timeline.append(
            {
                "actor": actor or "관련 메일",
                "timestamp": timestamp,
                "label": subject or "근거 메일",
                "state": "reference",
            }
        )
    deduped: list[dict[str, str]] = []
    seen: set[str] = set()
    for item in timeline:
        key = "|".join([item.get("actor", ""), item.get("timestamp", ""), item.get("label", "")])
        if key in seen:
            continue
        seen.add(key)
        deduped.append(item)
    return deduped[:3]
