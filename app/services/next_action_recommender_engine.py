from __future__ import annotations

import math
import os
import re
from functools import lru_cache
from typing import Any

from openai import AzureOpenAI, OpenAIError

from app.core.azure_openai_client import get_azure_openai_client, has_azure_openai_config, normalize_azure_deployment_name
from app.core.logging_config import get_logger
from app.services.next_action_recommender_domains import (
    ACTION_DOMAINS,
    CODE_ANALYSIS_ACTION_ID,
    CODE_EVIDENCE_PATTERNS,
    EMBEDDING_MODEL,
    MAX_EMBEDDING_INPUT_CHARS,
    MAX_NEXT_ACTIONS,
    ActionDomain,
)

logger = get_logger(__name__)


def recommend_next_actions(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any] | None = None,
    intent_task_type: str = "",
    intent_output_format: str = "",
) -> list[dict[str, str]]:
    """
    메일/응답 맥락에 가장 유사한 실행 가능 도메인 액션 Top3를 추천한다.

    Args:
        user_message: 사용자 질의 원문
        answer: 최종 답변
        tool_payload: 마지막 tool payload
        intent_task_type: 의도 task type
        intent_output_format: 의도 output format

    Returns:
        UI 표시용 `next_actions` 목록
    """
    payload = tool_payload if isinstance(tool_payload, dict) else {}
    context = _build_context_text(
        user_message=user_message,
        answer=answer,
        tool_payload=payload,
        intent_task_type=intent_task_type,
        intent_output_format=intent_output_format,
    )
    context_tokens = _tokenize(text=context)
    query_tokens = _tokenize(text=user_message)
    recent_tool_action = str(payload.get("action") or "").strip().lower()
    current_mail_available = _is_current_mail_available(tool_payload=payload)
    embedding_similarities = _resolve_embedding_similarities(context=context)

    scored: list[tuple[float, ActionDomain]] = []
    for domain in ACTION_DOMAINS:
        if not _is_domain_enabled(domain=domain):
            continue
        if domain.requires_current_mail and not current_mail_available:
            continue
        if not _is_domain_eligible(domain=domain, tool_payload=payload):
            continue
        score = _score_domain(
            domain=domain,
            context_tokens=context_tokens,
            query_tokens=query_tokens,
            recent_tool_action=recent_tool_action,
            intent_task_type=intent_task_type,
            intent_output_format=intent_output_format,
            embedding_similarity=embedding_similarities.get(domain.action_id),
        )
        if score <= 0:
            continue
        scored.append((score, domain))

    scored.sort(key=lambda item: item[0], reverse=True)
    top_domains = [item[1] for item in scored[:MAX_NEXT_ACTIONS]]
    return [_to_ui_action(domain=domain, score=scored[index][0]) for index, domain in enumerate(top_domains)]


def _is_domain_eligible(domain: ActionDomain, tool_payload: dict[str, Any]) -> bool:
    """
    도메인별 실행 가능 여부를 하드 규칙으로 판단한다.

    Args:
        domain: 액션 도메인
        tool_payload: 도구 payload

    Returns:
        후보 유지 가능하면 True
    """
    if domain.action_id != CODE_ANALYSIS_ACTION_ID:
        return True
    return _has_code_evidence(tool_payload=tool_payload)


def _has_code_evidence(tool_payload: dict[str, Any]) -> bool:
    """
    메일 컨텍스트에 코드 스니펫 증거가 있는지 확인한다.

    Args:
        tool_payload: 도구 payload

    Returns:
        코드 증거가 있으면 True
    """
    evidence_text = _build_code_evidence_text(tool_payload=tool_payload)
    if not evidence_text:
        return False
    return any(pattern.search(evidence_text) for pattern in CODE_EVIDENCE_PATTERNS)


def _build_code_evidence_text(tool_payload: dict[str, Any]) -> str:
    """
    코드 증거 탐지를 위한 텍스트를 조합한다.

    Args:
        tool_payload: 도구 payload

    Returns:
        코드 탐지 대상 텍스트
    """
    mail_context = tool_payload.get("mail_context")
    safe_mail_context = mail_context if isinstance(mail_context, dict) else {}
    parts = (
        str(tool_payload.get("body_preview") or ""),
        str(tool_payload.get("body_excerpt") or ""),
        str(safe_mail_context.get("body_preview") or ""),
        str(safe_mail_context.get("body_excerpt") or ""),
        str(safe_mail_context.get("body_code_excerpt") or ""),
        str(safe_mail_context.get("snippet") or ""),
    )
    merged = "\n".join(part for part in parts if part).strip()
    return merged[:MAX_EMBEDDING_INPUT_CHARS]


def _build_context_text(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
    intent_task_type: str,
    intent_output_format: str,
) -> str:
    """
    추천 스코어링용 문맥 텍스트를 구성한다.

    Args:
        user_message: 사용자 질의
        answer: 최종 답변
        tool_payload: 도구 payload
        intent_task_type: 의도 task type
        intent_output_format: 의도 output format

    Returns:
        결합된 문맥 텍스트
    """
    mail_context = tool_payload.get("mail_context")
    mail_context = mail_context if isinstance(mail_context, dict) else {}
    parts = [
        str(user_message or ""),
        str(answer or ""),
        str(intent_task_type or ""),
        str(intent_output_format or ""),
        str(tool_payload.get("subject") or ""),
        str(mail_context.get("subject") or ""),
        str(mail_context.get("summary_text") or ""),
        str(mail_context.get("body_preview") or ""),
    ]
    merged = "\n".join(part for part in parts if part).strip()
    return merged[:MAX_EMBEDDING_INPUT_CHARS]


def _is_current_mail_available(tool_payload: dict[str, Any]) -> bool:
    """
    현재메일 기반 액션 수행 가능 여부를 판단한다.

    Args:
        tool_payload: 도구 payload

    Returns:
        현재메일 컨텍스트가 있으면 True
    """
    action = str(tool_payload.get("action") or "").strip().lower()
    if action == "current_mail":
        return True
    mail_context = tool_payload.get("mail_context")
    if isinstance(mail_context, dict) and str(mail_context.get("message_id") or "").strip():
        return True
    return False


def _is_domain_enabled(domain: ActionDomain) -> bool:
    """
    액션 도메인의 기능 플래그를 확인한다.

    Args:
        domain: 액션 도메인

    Returns:
        기능이 활성화되어 있으면 True
    """
    raw = str(os.getenv(domain.capability_env, "1")).strip().lower()
    return raw not in {"0", "false", "off", "no"}


def _tokenize(text: str) -> set[str]:
    """
    한글/영문/숫자 토큰 집합으로 정규화한다.

    Args:
        text: 입력 텍스트

    Returns:
        토큰 집합
    """
    lowered = str(text or "").lower()
    pieces = re.findall(r"[a-z0-9가-힣]+", lowered)
    tokens: set[str] = set()
    for piece in pieces:
        if len(piece) <= 1:
            continue
        tokens.add(piece)
        if len(piece) >= 4:
            tokens.add(piece[:2])
            tokens.add(piece[-2:])
    return tokens


def _score_domain(
    domain: ActionDomain,
    context_tokens: set[str],
    query_tokens: set[str],
    recent_tool_action: str,
    intent_task_type: str,
    intent_output_format: str,
    embedding_similarity: float | None,
) -> float:
    """
    도메인 적합도를 하이브리드 방식으로 계산한다.

    Args:
        domain: 액션 도메인
        context_tokens: 문맥 토큰
        query_tokens: 사용자 질의 토큰
        recent_tool_action: 최근 tool action
        intent_task_type: 의도 task type
        intent_output_format: 의도 output format
        embedding_similarity: 선택적 임베딩 유사도

    Returns:
        최종 점수
    """
    keyword_tokens = _tokenize(text=" ".join(domain.keywords))
    title_tokens = _tokenize(text=domain.title + " " + domain.description)
    all_domain_tokens = keyword_tokens | title_tokens

    lexical_overlap = _overlap_ratio(source=context_tokens, target=all_domain_tokens)
    query_overlap = _overlap_ratio(source=query_tokens, target=all_domain_tokens)

    intent_text = f"{intent_task_type} {intent_output_format}".lower()
    intent_bonus = 0.0
    if any(hint in intent_text for hint in domain.intent_hints):
        intent_bonus = 0.18

    tool_bonus = 0.0
    if recent_tool_action and any(hint in recent_tool_action for hint in domain.tool_action_hints):
        tool_bonus = 0.16

    keyword_bonus = 0.0
    if any(keyword in " ".join(context_tokens) for keyword in domain.keywords):
        keyword_bonus = 0.12

    semantic_score = embedding_similarity if embedding_similarity is not None else 0.0
    base = (lexical_overlap * 0.48) + (query_overlap * 0.24) + (semantic_score * 0.28)
    return round(base + intent_bonus + tool_bonus + keyword_bonus, 4)


def _overlap_ratio(source: set[str], target: set[str]) -> float:
    """
    토큰 집합 간 겹침 비율을 계산한다.

    Args:
        source: 원본 토큰
        target: 비교 토큰

    Returns:
        0~1 범위 겹침 비율
    """
    if not source or not target:
        return 0.0
    intersection = source & target
    return len(intersection) / len(target)


def _to_ui_action(domain: ActionDomain, score: float) -> dict[str, str]:
    """
    내부 도메인 객체를 UI 계약 형태로 변환한다.

    Args:
        domain: 액션 도메인
        score: 추천 점수

    Returns:
        UI 액션 사전
    """
    priority = "low"
    if score >= 0.58:
        priority = "high"
    elif score >= 0.34:
        priority = "medium"
    return {
        "action_id": domain.action_id,
        "title": domain.title,
        "description": domain.description,
        "query": domain.query_template,
        "priority": priority,
    }


def _should_use_embeddings() -> bool:
    """
    임베딩 스코어 사용 여부를 확인한다.

    Returns:
        임베딩 사용 가능하면 True
    """
    use_flag = str(os.getenv("MOLDUBOT_ACTION_USE_EMBEDDING", "1")).strip().lower()
    if use_flag in {"0", "false", "off", "no"}:
        return False
    return has_azure_openai_config()


def _resolve_embedding_similarities(context: str) -> dict[str, float]:
    """
    컨텍스트와 액션 도메인 간 임베딩 유사도를 계산한다.

    Args:
        context: 추천 문맥 텍스트

    Returns:
        action_id별 유사도 맵
    """
    if not _should_use_embeddings():
        return {}
    safe_context = str(context or "").strip()
    if not safe_context:
        return {}

    domain_texts = [f"{d.title}\n{d.description}\n{' '.join(d.keywords)}" for d in ACTION_DOMAINS]
    try:
        deployment = _resolve_embedding_deployment()
        client = _get_embedding_client()
        domain_vectors = _get_domain_embeddings(domain_texts=tuple(domain_texts), deployment=deployment)
        query_embedding = client.embeddings.create(
            model=deployment,
            input=safe_context,
        ).data[0].embedding
    except OpenAIError as exc:
        logger.warning("next_action_recommender.embedding_failed: %s", exc)
        return {}

    similarities: dict[str, float] = {}
    for index, domain in enumerate(ACTION_DOMAINS):
        if index >= len(domain_vectors):
            continue
        similarities[domain.action_id] = _cosine_similarity(query_embedding, domain_vectors[index])
    return similarities


@lru_cache(maxsize=1)
def _get_domain_embeddings(domain_texts: tuple[str, ...], deployment: str) -> tuple[list[float], ...]:
    """
    도메인 설명 임베딩을 캐시 조회/생성한다.

    Args:
        domain_texts: 도메인 설명 텍스트 목록
        deployment: Azure 임베딩 배포명

    Returns:
        도메인 임베딩 튜플
    """
    client = _get_embedding_client()
    response = client.embeddings.create(model=deployment, input=list(domain_texts))
    return tuple(item.embedding for item in response.data)


@lru_cache(maxsize=1)
def _get_embedding_client() -> AzureOpenAI:
    """
    next_actions 임베딩 계산용 Azure OpenAI 클라이언트를 반환한다.

    Returns:
        Azure OpenAI SDK 클라이언트
    """
    return get_azure_openai_client(timeout_sec=45)


def _resolve_embedding_deployment() -> str:
    """
    임베딩 호출에 사용할 Azure 배포명을 해석한다.

    Returns:
        Azure 임베딩 배포명
    """
    raw = str(os.getenv("AZURE_OPENAI_EMBEDDING_DEPLOYMENT", EMBEDDING_MODEL)).strip()
    return normalize_azure_deployment_name(model_name=raw, default_deployment=EMBEDDING_MODEL)


def _cosine_similarity(vector_a: list[float], vector_b: list[float]) -> float:
    """
    두 벡터의 코사인 유사도를 계산한다.

    Args:
        vector_a: 벡터 A
        vector_b: 벡터 B

    Returns:
        코사인 유사도(0~1)
    """
    if not vector_a or not vector_b or len(vector_a) != len(vector_b):
        return 0.0
    dot = sum(a * b for a, b in zip(vector_a, vector_b))
    norm_a = math.sqrt(sum(a * a for a in vector_a))
    norm_b = math.sqrt(sum(b * b for b in vector_b))
    if norm_a == 0 or norm_b == 0:
        return 0.0
    raw = dot / (norm_a * norm_b)
    return max(0.0, min(1.0, (raw + 1.0) / 2.0))
