from __future__ import annotations

from dataclasses import dataclass
from functools import lru_cache
from typing import Literal

from app.agents.intent_schema import (
    IntentDecomposition,
    IntentFocusTopic,
    IntentOutputFormat,
    IntentTaskType,
)
from app.services.current_mail_grounded_safe_policy import (
    render_current_mail_grounded_safe_message,
    should_apply_current_mail_grounded_safe_guard,
)
from app.services.current_mail_intent_policy_fallback import (
    build_text_fallback_decomposition,
    has_current_mail_anchor_text,
    is_current_mail_decomposition,
)
from app.services.intent_decomposition_service import parse_intent_decomposition_safely


@dataclass(frozen=True)
class CurrentMailIntentContract:
    """
    현재메일 의도 판별에 사용하는 공통 계약 구조체.

    Attributes:
        has_anchor: 현재메일 문맥(anchor/scope/decomposition) 여부
        decomposition: 구조화 의도 결과
        allows_cause_analysis: 원인 분석 분기 허용 여부
        allows_solution: 해결 분기 허용 여부
        allows_direct_fact: direct fact 분기 허용 여부
        allows_translation: 번역 분기 허용 여부
    """

    has_anchor: bool
    decomposition: IntentDecomposition | None
    allows_cause_analysis: bool
    allows_solution: bool
    allows_direct_fact: bool
    allows_translation: bool


DirectFactTargetType = Literal[
    "general",
    "email_address",
    "domain",
    "sender",
    "recipient",
    "contact",
    "query",
]


@dataclass(frozen=True)
class DirectFactDecision:
    """
    현재메일 direct fact 분기 결정 결과.

    Attributes:
        enabled: direct fact 분기 허용 여부
        target_type: 추출 대상 타입
    """

    enabled: bool
    target_type: DirectFactTargetType = "general"


def is_current_mail_cause_analysis_request(user_message: str) -> bool:
    """
    현재메일 원인 분석 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        원인 분석 요청이면 True
    """
    contract = resolve_current_mail_intent_contract(user_message=user_message)
    if not contract.has_anchor or not contract.allows_cause_analysis:
        return False
    decomposition = contract.decomposition
    if decomposition is None:
        return False
    if decomposition.task_type not in (IntentTaskType.ANALYSIS, IntentTaskType.SOLUTION):
        return False
    compact = str(user_message or "").replace(" ", "")
    explicit_tokens = ("원인", "이유", "왜", "실패")
    return any(token in compact for token in explicit_tokens)


def is_current_mail_solution_request(user_message: str) -> bool:
    """
    현재메일 해결 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        해결 요청이면 True
    """
    contract = resolve_current_mail_intent_contract(user_message=user_message)
    if not contract.has_anchor or not contract.allows_solution:
        return False
    decomposition = contract.decomposition
    if decomposition is None:
        return False
    return decomposition.task_type == IntentTaskType.SOLUTION


def resolve_current_mail_issue_sections(user_message: str) -> tuple[str, ...]:
    """
    현재메일 이슈 분석 질의의 출력 섹션 계약을 계산한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        섹션 ID 튜플(`cause`, `impact`, `response`)
    """
    contract = resolve_current_mail_intent_contract(user_message=user_message)
    if not contract.has_anchor:
        return ()
    decomposition = contract.decomposition
    if decomposition is None:
        return ()
    if decomposition.output_format == IntentOutputFormat.ISSUE_ACTION:
        return ("cause", "response")
    if decomposition.task_type == IntentTaskType.SOLUTION:
        return ("cause", "response")
    if decomposition.task_type == IntentTaskType.ANALYSIS:
        return ("cause", "impact", "response")
    return ()


def is_current_mail_direct_fact_request(
    user_message: str,
    has_current_mail_context: bool = False,
    decomposition: IntentDecomposition | None = None,
) -> bool:
    """
    현재메일 맥락에서 특정 항목(주소/도메인/주체)을 직접 묻는 사실질의인지 판별한다.

    Args:
        user_message: 사용자 입력 원문
        has_current_mail_context: 외부 scope에서 current_mail이 확정된 경우 True
        decomposition: 구조화 의도 결과(있으면 우선 활용)

    Returns:
        직접 사실질의면 True
    """
    return resolve_current_mail_direct_fact_decision(
        user_message=user_message,
        has_current_mail_context=has_current_mail_context,
        decomposition=decomposition,
    ).enabled


def resolve_current_mail_direct_fact_decision(
    user_message: str,
    has_current_mail_context: bool = False,
    decomposition: IntentDecomposition | None = None,
) -> DirectFactDecision:
    """
    현재메일 direct fact 분기 허용/타깃 타입을 계산한다.

    Args:
        user_message: 사용자 입력 원문
        has_current_mail_context: 외부 scope에서 current_mail이 확정된 경우 True
        decomposition: 구조화 의도 결과(있으면 우선 활용)

    Returns:
        direct fact 결정 결과
    """
    target_type = _resolve_direct_fact_target_type(user_message=user_message)
    contract = resolve_current_mail_intent_contract(
        user_message=user_message,
        has_current_mail_context=has_current_mail_context,
        decomposition=decomposition,
    )
    if not contract.has_anchor or not contract.allows_direct_fact:
        return DirectFactDecision(enabled=False, target_type="general")
    if is_translation_like_request_text(user_message=user_message):
        return DirectFactDecision(enabled=False, target_type=target_type)
    if not _has_direct_fact_entity_signal(user_message=user_message):
        return DirectFactDecision(enabled=False, target_type="general")

    resolved = contract.decomposition
    if resolved is None:
        return DirectFactDecision(enabled=True, target_type=target_type)
    if resolved.task_type in (IntentTaskType.SUMMARY, IntentTaskType.SOLUTION, IntentTaskType.ACTION):
        return DirectFactDecision(enabled=False, target_type="general")
    if resolved.task_type == IntentTaskType.RETRIEVAL and IntentFocusTopic.RECIPIENTS in resolved.focus_topics:
        return DirectFactDecision(enabled=True, target_type=target_type)
    if IntentFocusTopic.RECIPIENTS in resolved.focus_topics:
        return DirectFactDecision(enabled=True, target_type=target_type)
    return DirectFactDecision(enabled=True, target_type=target_type)


def _has_direct_fact_entity_signal(user_message: str) -> bool:
    """
    direct fact로 해석 가능한 명시적 엔터티 질의 신호를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        엔터티 직접값 질의 신호가 있으면 True
    """
    compact = str(user_message or "").replace(" ", "").lower()
    if not compact:
        return False
    entity_tokens = (
        "메일주소",
        "이메일주소",
        "도메인",
        "ou",
        "발신자",
        "수신자",
        "담당자",
        "문의처",
        "연락처",
        "from",
        "to",
        "주체",
        "어느팀",
        "누구",
        "누가",
    )
    if any(token in compact for token in entity_tokens):
        return True
    if "어디로" in compact and ("연락" in compact or "문의" in compact):
        return True
    return False


def _resolve_direct_fact_target_type(user_message: str) -> DirectFactTargetType:
    """
    사용자 질의의 direct fact 타깃 타입을 텍스트 신호로 분류한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        direct fact 타깃 타입
    """
    compact = str(user_message or "").replace(" ", "").lower()
    if not compact:
        return "general"
    if "도메인" in compact:
        return "domain"
    if any(token in compact for token in ("메일주소", "이메일주소")):
        return "email_address"
    if "주소" in compact and "메일" in compact:
        return "email_address"
    if any(token in compact for token in ("발신자", "from")):
        return "sender"
    if any(token in compact for token in ("수신자", "to")):
        return "recipient"
    if any(token in compact for token in ("문의처", "연락처")):
        return "contact"
    if "어디로" in compact and ("연락" in compact or "문의" in compact):
        return "contact"
    if any(token in compact for token in ("ou", "쿼리", "query", "명령")):
        return "query"
    return "general"


def is_current_mail_translation_request(
    user_message: str,
    has_current_mail_context: bool = False,
    decomposition: IntentDecomposition | None = None,
) -> bool:
    """
    현재메일 맥락에서 번역 요청인지 판별한다.

    Args:
        user_message: 사용자 입력 원문
        has_current_mail_context: 외부 scope에서 current_mail로 확정된 경우 True
        decomposition: 구조화 의도 결과(있으면 우선 활용)

    Returns:
        현재메일 번역 요청이면 True
    """
    contract = resolve_current_mail_intent_contract(
        user_message=user_message,
        has_current_mail_context=has_current_mail_context,
        decomposition=decomposition,
    )
    if not contract.has_anchor or not contract.allows_translation:
        return False
    if is_translation_like_request_text(user_message=user_message):
        return True
    if contract.decomposition is None:
        return False
    return contract.decomposition.output_format == IntentOutputFormat.TRANSLATION


def is_translation_like_request_text(user_message: str) -> bool:
    """
    사용자 문장이 번역 요청 성격인지 텍스트 기준으로 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        번역 성격 요청이면 True
    """
    compact = str(user_message or "").replace(" ", "").lower()
    if not compact:
        return False
    translation_tokens = ("번역", "translate", "translation")
    return any(token in compact for token in translation_tokens)


def resolve_current_mail_intent_contract(
    user_message: str,
    has_current_mail_context: bool = False,
    decomposition: IntentDecomposition | None = None,
) -> CurrentMailIntentContract:
    """
    현재메일 의도 판별 공통 계약을 계산한다.

    Args:
        user_message: 사용자 입력 원문
        has_current_mail_context: scope로 current_mail이 확정된 경우 True
        decomposition: 구조화 의도 결과(있으면 우선 활용)

    Returns:
        현재메일 의도 공통 계약
    """
    resolved = _resolve_decomposition(
        user_message=user_message,
        has_current_mail_context=has_current_mail_context,
        decomposition=decomposition,
    )
    has_anchor = (
        bool(has_current_mail_context)
        or is_current_mail_decomposition(decomposition=resolved)
        or has_current_mail_anchor_text(user_message=user_message)
    )
    return CurrentMailIntentContract(
        has_anchor=has_anchor,
        decomposition=resolved,
        allows_cause_analysis=(
            True
            if resolved is None
            else resolved.task_type in (IntentTaskType.ANALYSIS, IntentTaskType.SOLUTION, IntentTaskType.GENERAL)
        ),
        allows_solution=(
            True
            if resolved is None
            else resolved.task_type in (IntentTaskType.SOLUTION, IntentTaskType.ANALYSIS, IntentTaskType.GENERAL)
        ),
        allows_direct_fact=(
            True
            if resolved is None
            else resolved.task_type in (
                IntentTaskType.EXTRACTION,
                IntentTaskType.RETRIEVAL,
                IntentTaskType.GENERAL,
            )
        ),
        allows_translation=(
            True
            if resolved is None
            else resolved.task_type in (
                IntentTaskType.GENERAL,
                IntentTaskType.SUMMARY,
                IntentTaskType.RETRIEVAL,
                IntentTaskType.EXTRACTION,
            )
        ),
    )


def _resolve_decomposition(
    user_message: str,
    has_current_mail_context: bool,
    decomposition: IntentDecomposition | None,
) -> IntentDecomposition | None:
    """
    현재 질의에 대한 decomposition을 안전하게 확보한다.

    Args:
        user_message: 사용자 질의
        has_current_mail_context: scope에서 current_mail이 확정됐는지 여부
        decomposition: 외부에서 전달된 decomposition

    Returns:
        확보된 decomposition 또는 None
    """
    if decomposition is not None:
        return decomposition
    normalized = str(user_message or "").strip()
    if not normalized:
        return None
    return _parse_intent_decomposition_cached(
        user_message=normalized,
        has_current_mail_context=bool(has_current_mail_context),
    )


@lru_cache(maxsize=512)
def _parse_intent_decomposition_cached(
    user_message: str,
    has_current_mail_context: bool,
) -> IntentDecomposition | None:
    """
    동일 입력 decomposition 파싱 결과를 캐시한다.

    Args:
        user_message: 정규화된 사용자 질의
        has_current_mail_context: scope current_mail 확정 여부

    Returns:
        구조화 의도 결과 또는 None
    """
    parsed = parse_intent_decomposition_safely(
        user_message=user_message,
        has_selected_mail=bool(has_current_mail_context),
        selected_message_id_exists=bool(has_current_mail_context),
    )
    if parsed is not None:
        return parsed
    return build_text_fallback_decomposition(
        user_message=user_message,
        has_current_mail_context=has_current_mail_context,
        has_anchor_fn=has_current_mail_anchor_text,
        has_direct_fact_entity_signal_fn=_has_direct_fact_entity_signal,
        is_translation_like_request_text_fn=is_translation_like_request_text,
    )


__all__ = [
    "CurrentMailIntentContract",
    "DirectFactDecision",
    "is_current_mail_cause_analysis_request",
    "is_current_mail_solution_request",
    "resolve_current_mail_issue_sections",
    "is_current_mail_direct_fact_request",
    "resolve_current_mail_direct_fact_decision",
    "is_current_mail_translation_request",
    "is_translation_like_request_text",
    "resolve_current_mail_intent_contract",
    "render_current_mail_grounded_safe_message",
    "should_apply_current_mail_grounded_safe_guard",
]
