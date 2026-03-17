from __future__ import annotations

import os
import re
from typing import Any

from app.core.llm_runtime import invoke_json_object, is_model_provider_configured, resolve_env_model
from app.core.logging_config import get_logger
from app.services.next_action_recommender_domains import (
    ACTION_DOMAINS,
    CODE_ANALYSIS_ACTION_ID,
    CODE_EVIDENCE_PATTERNS,
    MAX_EMBEDDING_INPUT_CHARS,
    MAX_NEXT_ACTIONS,
    ActionDomain,
)

logger = get_logger(__name__)
DEFAULT_ACTION_SELECTOR_MODE = "llm"
ACTION_SELECTOR_MODE_ENV = "MOLDUBOT_ACTION_SELECTOR_MODE"
ACTION_SELECTOR_MODEL_ENV = "MOLDUBOT_ACTION_SELECTOR_MODEL"
DEFAULT_ACTION_SELECTOR_MODEL = "gpt-4o-mini"
ACTION_SELECTOR_TIMEOUT_SEC = 12
ACTION_SELECTOR_CANDIDATE_LIMIT = 6


def recommend_next_actions(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any] | None = None,
    intent_task_type: str = "",
    intent_output_format: str = "",
    selector_mode_override: str | None = None,
    allow_embeddings: bool = True,
) -> list[dict[str, str]]:
    """
    메일/응답 맥락에 가장 유사한 실행 가능 도메인 액션 Top3를 추천한다.

    Args:
        user_message: 사용자 질의 원문
        answer: 최종 답변
        tool_payload: 마지막 tool payload
        intent_task_type: 의도 task type
        intent_output_format: 의도 output format
        selector_mode_override: 추천 모드 강제값(`llm`/`score`)
        allow_embeddings: 임베딩 유사도 계산 허용 여부

    Returns:
        UI 표시용 `next_actions` 목록
    """
    _ = allow_embeddings  # backward-compatible 인자 유지
    selector_mode = _resolve_selector_mode(override=selector_mode_override)
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
        )
        if score <= 0:
            continue
        scored.append((score, domain))

    scored.sort(key=lambda item: item[0], reverse=True)
    if not scored:
        return []

    if selector_mode == "llm":
        llm_selected = _select_actions_with_llm(
            scored_domains=scored,
            user_message=user_message,
            answer=answer,
            tool_payload=payload,
            intent_task_type=intent_task_type,
            intent_output_format=intent_output_format,
        )
        if llm_selected:
            return llm_selected

    top_domains = [item[1] for item in scored[:MAX_NEXT_ACTIONS]]
    return [_to_ui_action(domain=domain, score=scored[index][0]) for index, domain in enumerate(top_domains)]


def resolve_next_actions_from_action_ids(
    action_ids: list[str],
    tool_payload: dict[str, Any] | None = None,
) -> list[dict[str, str]]:
    """
    LLM이 고른 action_id 목록을 UI 카드 계약으로 변환한다.

    Args:
        action_ids: LLM 제안 action_id 목록
        tool_payload: 현재 툴 payload

    Returns:
        UI 표시용 next action 목록
    """
    payload = tool_payload if isinstance(tool_payload, dict) else {}
    current_mail_available = _is_current_mail_available(tool_payload=payload)
    selected_ids = _normalize_selected_action_ids(raw=action_ids)
    if not selected_ids:
        return []
    domain_by_id = {domain.action_id: domain for domain in ACTION_DOMAINS}
    actions: list[dict[str, str]] = []
    for action_id in selected_ids:
        domain = domain_by_id.get(action_id)
        if domain is None:
            continue
        if not _is_domain_enabled(domain=domain):
            continue
        if domain.requires_current_mail and not current_mail_available:
            continue
        if not _is_domain_eligible(domain=domain, tool_payload=payload):
            continue
        actions.append(_to_ui_action(domain=domain, score=0.58))
        if len(actions) >= MAX_NEXT_ACTIONS:
            break
    return actions


def _resolve_selector_mode(override: str | None = None) -> str:
    """
    후속 액션 추천기 선택 모드를 해석한다.

    Args:
        override: 런타임 강제 모드

    Returns:
        `llm` 또는 `score`
    """
    if override is not None:
        raw = str(override).strip().lower()
    else:
        raw = str(os.getenv(ACTION_SELECTOR_MODE_ENV, DEFAULT_ACTION_SELECTOR_MODE)).strip().lower()
    if raw in {"llm", "score"}:
        return raw
    return DEFAULT_ACTION_SELECTOR_MODE


def _select_actions_with_llm(
    scored_domains: list[tuple[float, ActionDomain]],
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
    intent_task_type: str,
    intent_output_format: str,
) -> list[dict[str, str]]:
    """
    점수 기반 후보군에서 LLM이 최종 1~3개 액션을 선택하도록 실행한다.

    Args:
        scored_domains: 점수순 도메인 목록
        user_message: 사용자 질의 원문
        answer: 최종 답변
        tool_payload: 도구 payload
        intent_task_type: 의도 task type
        intent_output_format: 의도 output format

    Returns:
        UI 표시용 next action 목록. 실패 시 빈 배열
    """
    candidate_pairs = scored_domains[:ACTION_SELECTOR_CANDIDATE_LIMIT]
    if not candidate_pairs:
        return []
    model_name = resolve_env_model(
        primary_env=ACTION_SELECTOR_MODEL_ENV,
        fallback_envs=("MOLDUBOT_AGENT_MODEL", "DEFAULT_CHAT_MODEL"),
        default_model=DEFAULT_ACTION_SELECTOR_MODEL,
    )
    if not is_model_provider_configured(model_name=model_name):
        return []
    candidate_lines: list[str] = []
    for index, (score, domain) in enumerate(candidate_pairs, start=1):
        candidate_lines.append(
            f"{index}. action_id={domain.action_id} | title={domain.title} | desc={domain.description} | score={score:.3f}"
        )
    system_prompt = (
        "너는 후속작업 카드 선택기다. 후보 action_id 중에서 사용자에게 유용한 1~3개만 고른다.\n"
        "반드시 JSON 객체 1개만 출력한다. 스키마: {\"action_ids\":[\"id1\",\"id2\"]}\n"
        "규칙: 후보에 없는 action_id 금지, 중복 금지, 최대 3개."
    )
    user_prompt = (
        f"[user_message]\n{str(user_message or '').strip()}\n\n"
        f"[answer]\n{str(answer or '').strip()[:1200]}\n\n"
        f"[intent]\n{intent_task_type}/{intent_output_format}\n\n"
        f"[tool_action]\n{str(tool_payload.get('action') or '').strip()}\n\n"
        f"[candidates]\n" + "\n".join(candidate_lines)
    )
    try:
        llm_json = invoke_json_object(
            model_name=model_name,
            system_prompt=system_prompt,
            user_prompt=user_prompt,
            timeout_sec=ACTION_SELECTOR_TIMEOUT_SEC,
            temperature=0.0,
        )
    except (ValueError, RuntimeError, TypeError) as exc:
        logger.warning("next_action_recommender.selector_failed: %s", exc)
        return []

    selected_action_ids = _normalize_selected_action_ids(raw=llm_json.get("action_ids"))
    selected_by_id: dict[str, tuple[float, ActionDomain]] = {
        domain.action_id: (score, domain) for score, domain in candidate_pairs
    }
    selected_actions: list[dict[str, str]] = []
    for action_id in selected_action_ids:
        pair = selected_by_id.get(action_id)
        if pair is None:
            continue
        score, domain = pair
        selected_actions.append(_to_ui_action(domain=domain, score=score))
        if len(selected_actions) >= MAX_NEXT_ACTIONS:
            break
    return selected_actions


def _normalize_selected_action_ids(raw: object) -> list[str]:
    """
    LLM 응답의 action_ids를 문자열 리스트로 정규화한다.

    Args:
        raw: 원본 action_ids 값

    Returns:
        중복 제거된 action_id 목록
    """
    if not isinstance(raw, list):
        return []
    normalized: list[str] = []
    seen: set[str] = set()
    for item in raw:
        action_id = str(item or "").strip().lower()
        if not action_id or action_id in seen:
            continue
        seen.add(action_id)
        normalized.append(action_id)
    return normalized[:MAX_NEXT_ACTIONS]


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

    base = (lexical_overlap * 0.62) + (query_overlap * 0.38)
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
