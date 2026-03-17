from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from app.agents.intent_schema import IntentDecomposition, IntentFocusTopic, IntentTaskType
from app.api.followup_scope import get_recent_search_result_count
from app.api.search_chat_metadata import build_context_enrichment
from app.api.search_chat_next_actions_runtime import should_suppress_web_sources
from app.core.logging_config import get_logger
from app.models.response_contracts import RecipientRoleEntry, RecipientTodoEntry
from app.services.answer_postprocessor_contract_utils import parse_llm_response_contract
from app.services.mail_search_service import MailSearchService
from app.services.semantic_answer_contract import build_semantic_answer_contract
from app.services.web_source_search_service import (
    get_web_verification_reasons,
    search_web_sources,
    should_search_web_sources,
)

logger = get_logger(__name__)


@dataclass(frozen=True)
class PostprocessExecutionPolicy:
    """
    postprocess 단계에서 수행/스킵할 세부 작업 정책.

    Attributes:
        skip_web_sources: 웹 출처 해소 단계 스킵 여부
        skip_related_mail_enrichment: 주요 포인트 관련메일 보강 단계 스킵 여부
    """

    skip_web_sources: bool
    skip_related_mail_enrichment: bool


def decide_postprocess_execution_policy(
    intent_output_format: str,
    tool_action: str,
    resolved_scope: str,
) -> PostprocessExecutionPolicy:
    """
    output_format/tool_action 조합으로 postprocess 실행 정책을 결정한다.

    Args:
        intent_output_format: 의도 분해 output_format 값
        tool_action: 마지막 tool action 값
        resolved_scope: 최종 scope 값

    Returns:
        postprocess 실행 정책 객체
    """
    normalized_output_format = str(intent_output_format or "").strip().lower()
    normalized_tool_action = str(tool_action or "").strip().lower()
    del resolved_scope
    should_skip_expensive_steps = (
        normalized_output_format == "general"
        and normalized_tool_action != "mail_search"
    )
    return PostprocessExecutionPolicy(
        skip_web_sources=should_skip_expensive_steps,
        skip_related_mail_enrichment=should_skip_expensive_steps,
    )


def build_search_scope_contract(
    user_message: str,
    resolved_scope: str,
    intent_decomposition: IntentDecomposition | None,
    is_current_mail_mode: bool,
) -> dict[str, str]:
    """
    도구 실행에 전달할 검색 scope 계약을 생성한다.

    Args:
        user_message: 사용자 입력
        resolved_scope: 최종 scope
        intent_decomposition: 의도 구조분해 결과
        is_current_mail_mode: 현재메일 범위 질의 여부

    Returns:
        scope 계약 사전
    """
    mode = str(resolved_scope or "").strip().lower()
    if not mode:
        mode = "current_mail" if is_current_mail_mode else "global_search"
    anchor_query = ""
    decomposition = intent_decomposition
    focus_topics = set(decomposition.focus_topics or []) if decomposition is not None else set()
    if decomposition is not None and decomposition.task_type == IntentTaskType.RETRIEVAL and (
        IntentFocusTopic.SCHEDULE in focus_topics or IntentFocusTopic.TECH_ISSUE in focus_topics
    ):
        anchor_query = _extract_scope_anchor_query(user_message=user_message)
    return {
        "mode": mode,
        "anchor_query": anchor_query,
    }


def build_scope_metadata(
    resolved_scope: str,
    is_current_mail_mode: bool,
    selected_message_id: str,
    thread_id: str,
) -> dict[str, str]:
    """
    UI 표시용 scope 라벨/설명 메타데이터를 생성한다.

    Args:
        resolved_scope: 최종 scope
        is_current_mail_mode: 현재메일 범위 질의 여부
        selected_message_id: 선택 메일 ID
        thread_id: 스레드 ID

    Returns:
        scope UI 메타데이터 사전
    """
    scope = str(resolved_scope or "").strip().lower()
    if scope == "current_mail":
        return {
            "scope_label": "현재 선택 메일",
            "scope_reason": "현재 메일 1건 기준으로 분석합니다.",
        }
    if scope == "previous_results":
        recent_count = get_recent_search_result_count(thread_id=thread_id, ttl_sec=600)
        return {
            "scope_label": "직전 조회 결과",
            "scope_reason": f"직전 조회 결과 {max(recent_count, 0)}건 범위에서 분석합니다.",
        }
    if scope == "global_search":
        return {
            "scope_label": "전체 사서함",
            "scope_reason": "선택 메일에 고정하지 않고 전체 사서함에서 검색합니다.",
        }
    if is_current_mail_mode and selected_message_id:
        return {
            "scope_label": "현재 선택 메일",
            "scope_reason": "현재 메일 1건 기준으로 분석합니다.",
        }
    return {
        "scope_label": "전체 사서함",
        "scope_reason": "전체 사서함 기준으로 분석합니다.",
    }


def enrich_major_point_related_mails(
    rows: list[dict[str, object]],
    tool_payload: dict[str, Any],
    mail_search_service: MailSearchService,
) -> list[dict[str, object]]:
    """
    주요 내용 근거에 벡터 검색 기반 관련 메일 근거를 보강한다.

    Args:
        rows: 주요 내용 근거 행 목록
        tool_payload: 마지막 도구 payload
        mail_search_service: 메일 검색 서비스

    Returns:
        관련 메일 근거가 보강된 행 목록
    """
    if not isinstance(rows, list):
        return []
    mail_context = tool_payload.get("mail_context") if isinstance(tool_payload, dict) else {}
    mail_context = mail_context if isinstance(mail_context, dict) else {}
    excluded_message_id = str(mail_context.get("message_id") or "").strip()
    enriched: list[dict[str, object]] = []
    for row in rows[:6]:
        if not isinstance(row, dict):
            continue
        updated = dict(row)
        point = str(row.get("point") or "").strip()
        updated["related_mails"] = _search_related_mails_for_point(
            point=point,
            excluded_message_id=excluded_message_id,
            limit=2,
            mail_search_service=mail_search_service,
        )
        enriched.append(updated)
    return enriched


def serialize_recipient_roles(rows: list[RecipientRoleEntry]) -> list[dict[str, str]]:
    """
    LLM 계약의 recipient_roles를 metadata 직렬화 형태로 변환한다.

    Args:
        rows: recipient_roles 행 목록

    Returns:
        직렬화된 recipient role 목록
    """
    normalized: list[dict[str, str]] = []
    for row in rows:
        recipient = str(getattr(row, "recipient", "") or "").strip()
        role = str(getattr(row, "role", "") or "").strip()
        evidence = str(getattr(row, "evidence", "") or "").strip()
        if not recipient:
            continue
        normalized.append({"recipient": recipient, "role": role, "evidence": evidence})
    return normalized[:8]


def serialize_recipient_todos(rows: list[RecipientTodoEntry]) -> list[dict[str, str]]:
    """
    LLM 계약의 recipient_todos를 metadata 직렬화 형태로 변환한다.

    Args:
        rows: recipient_todos 행 목록

    Returns:
        직렬화된 recipient todo 목록
    """
    normalized: list[dict[str, str]] = []
    for row in rows:
        recipient = str(getattr(row, "recipient", "") or "").strip()
        todo = str(getattr(row, "todo", "") or "").strip()
        due_date = str(getattr(row, "due_date", "") or "").strip()
        due_date_basis = str(getattr(row, "due_date_basis", "") or "").strip()
        if not recipient:
            continue
        normalized.append(
            {
                "recipient": recipient,
                "todo": todo,
                "due_date": due_date,
                "due_date_basis": due_date_basis,
            }
        )
    return normalized[:8]




def _extract_scope_anchor_query(user_message: str) -> str:
    """
    복합 조회 질의에서 기술 이슈 축과 결합할 앵커 키워드를 추출한다.

    Args:
        user_message: 사용자 입력

    Returns:
        앵커 문자열
    """
    text = str(user_message or "").strip()
    if not text:
        return ""
    normalized = re.sub(r"\s+", " ", text)
    for token in ("기술적 이슈", "기술 이슈", "이슈"):
        if token in normalized:
            head = normalized.split(token, 1)[0].strip(" ,.")
            return head[:64]
    head = normalized.split(".", 1)[0].strip(" ,.")
    return head[:64]


def _search_related_mails_for_point(
    point: str,
    excluded_message_id: str,
    limit: int,
    mail_search_service: MailSearchService,
) -> list[dict[str, str]]:
    """
    주요 내용 문장과 유사한 메일 근거를 조회한다.

    Args:
        point: 주요 내용 문장
        excluded_message_id: 현재 메일 ID(중복 제거)
        limit: 반환 개수 상한
        mail_search_service: 메일 검색 서비스

    Returns:
        관련 메일 근거 목록
    """
    query = str(point or "").strip()
    if not query:
        return []
    payload = mail_search_service.search(query=query, limit=max(4, limit * 2))
    results = payload.get("results") if isinstance(payload, dict) else []
    if not isinstance(results, list):
        return []
    normalized: list[dict[str, str]] = []
    seen_message_ids: set[str] = set()
    for item in results:
        if not isinstance(item, dict):
            continue
        message_id = str(item.get("message_id") or "").strip()
        if not message_id:
            continue
        if excluded_message_id and message_id == excluded_message_id:
            continue
        if message_id in seen_message_ids:
            continue
        seen_message_ids.add(message_id)
        snippet = str(item.get("snippet") or item.get("summary_text") or "").strip()
        if not _has_major_point_overlap(point=point, snippet=snippet):
            continue
        normalized.append(
            {
                "message_id": message_id,
                "subject": str(item.get("subject") or "제목 없음").strip() or "제목 없음",
                "received_date": str(item.get("received_date") or "-").strip() or "-",
                "sender_names": str(item.get("sender_names") or "-").strip() or "-",
                "snippet": snippet[:180],
                "web_link": str(item.get("web_link") or "").strip(),
            }
        )
        if len(normalized) >= limit:
            break
    return normalized


def _has_major_point_overlap(point: str, snippet: str) -> bool:
    """
    주요 내용과 후보 메일 스니펫의 최소 토큰 겹침 여부를 확인한다.

    Args:
        point: 주요 내용
        snippet: 후보 메일 스니펫

    Returns:
        토큰 겹침이 있으면 True
    """
    point_tokens = _extract_overlap_tokens(text=point)
    snippet_tokens = _extract_overlap_tokens(text=snippet)
    if not point_tokens or not snippet_tokens:
        return False
    return bool(point_tokens.intersection(snippet_tokens))


def _extract_overlap_tokens(text: str) -> set[str]:
    """
    겹침 판정용 토큰 집합을 추출한다.

    Args:
        text: 입력 텍스트

    Returns:
        정규화 토큰 집합
    """
    stop_words = {"현재", "관련", "요청", "확인", "필요", "검토", "내용", "메일", "대해", "기반"}
    tokens = re.findall(r"[A-Za-z0-9가-힣]{2,}", str(text or "").lower())
    return {token for token in tokens if token not in stop_words}


def resolve_web_sources_for_answer(
    user_message: str,
    intent_task_type: str,
    resolved_scope: str,
    tool_payload: dict[str, Any],
    intent_confidence: float | None,
    model_answer: str,
    next_action_id: str,
) -> tuple[list[dict[str, str]], list[str]]:
    """
    웹출처 검색 정책 판단과 실제 검색을 수행한다.

    Args:
        user_message: 사용자 질의
        intent_task_type: 의도 task type
        resolved_scope: 최종 scope
        tool_payload: 최근 도구 payload
        intent_confidence: 의도 confidence
        model_answer: 모델 응답
        next_action_id: next-action 식별자

    Returns:
        (웹 출처 목록, 정책 판단 근거 목록)
    """
    reasons = get_web_verification_reasons(
        user_message=user_message,
        intent_task_type=intent_task_type,
        resolved_scope=resolved_scope,
        tool_payload=tool_payload,
        intent_confidence=intent_confidence,
        model_answer=model_answer,
    )
    if should_suppress_web_sources(next_action_id=next_action_id):
        return ([], reasons)
    enabled = should_search_web_sources(
        user_message=user_message,
        intent_task_type=intent_task_type,
        resolved_scope=resolved_scope,
        tool_payload=tool_payload,
        intent_confidence=intent_confidence,
        model_answer=model_answer,
    )
    if not enabled:
        return ([], reasons)
    sources = search_web_sources(
        user_message=user_message,
        intent_task_type=intent_task_type,
        tool_payload=tool_payload,
    )
    return (sources, reasons)


def build_enrichment_payloads(
    answer: str,
    answer_format: dict[str, Any],
    tool_payload: dict[str, Any],
    evidence_mails: list[dict[str, str]],
    next_actions: list[dict[str, str]],
    intent_confidence: float,
    web_sources: list[dict[str, str]],
) -> tuple[object, list[dict[str, str]], list[dict[str, str]], dict[str, Any], dict[str, object]]:
    """
    응답 enrichment/semantic payload를 생성한다.

    Args:
        answer: 최종 응답
        answer_format: answer format metadata
        tool_payload: 도구 payload
        evidence_mails: 근거메일 목록
        next_actions: 추천 액션
        intent_confidence: 의도 confidence
        web_sources: 웹 출처 목록

    Returns:
        (parsed_contract, recipient_roles, recipient_todos, context_enrichment, semantic_contract)
    """
    parsed_contract = parse_llm_response_contract(raw_answer=answer, log_failures=False)
    roles = serialize_recipient_roles(rows=list(parsed_contract.recipient_roles) if parsed_contract is not None else [])
    todos = serialize_recipient_todos(rows=list(parsed_contract.recipient_todos) if parsed_contract is not None else [])
    context_enrichment = build_context_enrichment(
        answer=answer,
        answer_format=answer_format,
        tool_payload=tool_payload,
        evidence_mails=evidence_mails,
        next_actions=next_actions,
        llm_recipient_roles=roles,
        llm_recipient_todos=todos,
    )
    semantic_contract = build_semantic_answer_contract(
        contract=parsed_contract,
        answer=answer,
        intent_confidence=float(intent_confidence),
        evidence_mails=evidence_mails,
        web_sources=web_sources,
    )
    return (parsed_contract, roles, todos, context_enrichment, semantic_contract)
