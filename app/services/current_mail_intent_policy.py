from __future__ import annotations

from dataclasses import dataclass

from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    IntentFocusTopic,
    IntentOutputFormat,
    IntentTaskType,
)
from app.services.current_mail_grounded_safe_policy import (
    render_current_mail_grounded_safe_message,
    should_apply_current_mail_grounded_safe_guard,
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
    return decomposition.task_type in (IntentTaskType.ANALYSIS, IntentTaskType.SOLUTION)


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
    if decomposition.output_format == IntentOutputFormat.ISSUE_ACTION:
        return True
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
    contract = resolve_current_mail_intent_contract(
        user_message=user_message,
        has_current_mail_context=has_current_mail_context,
        decomposition=decomposition,
    )
    if not contract.has_anchor or not contract.allows_direct_fact:
        return False
    if is_translation_like_request_text(user_message=user_message):
        return False
    if not _has_direct_fact_entity_signal(user_message=user_message):
        return False

    resolved = contract.decomposition
    if resolved is None:
        return True
    if resolved.task_type in (IntentTaskType.SUMMARY, IntentTaskType.SOLUTION, IntentTaskType.ACTION):
        return False
    if resolved.task_type == IntentTaskType.RETRIEVAL and IntentFocusTopic.RECIPIENTS in resolved.focus_topics:
        return True
    if IntentFocusTopic.RECIPIENTS in resolved.focus_topics:
        return True
    return True


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


def is_current_mail_artifact_analysis_request(
    user_message: str,
    has_current_mail_context: bool = False,
) -> bool:
    """
    현재메일 맥락에서 본문 구문(쿼리/명령/코드 등) 분석 요청인지 판별한다.

    Args:
        user_message: 사용자 입력 원문
        has_current_mail_context: 외부 scope에서 current_mail로 이미 확정된 경우 True

    Returns:
        구문 분석 요청이면 True
    """
    contract = resolve_current_mail_intent_contract(
        user_message=user_message,
        has_current_mail_context=has_current_mail_context,
    )
    if not contract.has_anchor:
        return False
    decomposition = contract.decomposition
    if decomposition is None:
        return False
    if decomposition.task_type != IntentTaskType.ANALYSIS:
        return False
    target_topics = {IntentFocusTopic.TECH_ISSUE, IntentFocusTopic.SSL}
    return bool(target_topics.intersection(set(decomposition.focus_topics)))


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


def has_current_mail_anchor(user_message: str) -> bool:
    """
    입력 문장이 현재메일 문맥으로 해석되는지 반환한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        현재메일 문맥으로 해석되면 True
    """
    contract = resolve_current_mail_intent_contract(user_message=user_message)
    return contract.has_anchor


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
        or _is_current_mail_decomposition(decomposition=resolved)
        or _has_current_mail_anchor_text(user_message=user_message)
    )
    return CurrentMailIntentContract(
        has_anchor=has_anchor,
        decomposition=resolved,
        allows_cause_analysis=_allows_cause_analysis(decomposition=resolved),
        allows_solution=_allows_solution(decomposition=resolved),
        allows_direct_fact=_allows_direct_fact(decomposition=resolved),
        allows_translation=_allows_translation(decomposition=resolved),
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
    parsed = parse_intent_decomposition_safely(
        user_message=normalized,
        has_selected_mail=bool(has_current_mail_context),
        selected_message_id_exists=bool(has_current_mail_context),
    )
    if parsed is not None:
        return parsed
    return _build_text_fallback_decomposition(
        user_message=normalized,
        has_current_mail_context=has_current_mail_context,
    )


def _build_text_fallback_decomposition(
    user_message: str,
    has_current_mail_context: bool,
) -> IntentDecomposition | None:
    """
    LLM 구조분해 실패 시 텍스트 신호 기반 최소 decomposition을 생성한다.

    Args:
        user_message: 사용자 질의
        has_current_mail_context: scope current_mail 확정 여부

    Returns:
        추론된 decomposition 또는 None
    """
    if not has_current_mail_context and not _has_current_mail_anchor_text(user_message=user_message):
        return None
    compact = str(user_message or "").replace(" ", "").lower()
    is_translation = is_translation_like_request_text(user_message=user_message)
    has_cause_token = any(token in compact for token in ("원인", "이유", "왜", "문제", "이슈"))
    has_solution_token = any(token in compact for token in ("해결", "대응", "조치", "방안", "방법"))
    has_summary_token = any(token in compact for token in ("요약", "정리", "핵심", "주요"))
    if is_translation:
        task_type = IntentTaskType.GENERAL
        output_format = IntentOutputFormat.TRANSLATION
    elif has_solution_token:
        task_type = IntentTaskType.SOLUTION
        output_format = IntentOutputFormat.ISSUE_ACTION if has_cause_token else IntentOutputFormat.GENERAL
    elif has_cause_token:
        task_type = IntentTaskType.ANALYSIS
        output_format = IntentOutputFormat.GENERAL
    elif _has_direct_fact_entity_signal(user_message=user_message):
        task_type = IntentTaskType.EXTRACTION
        output_format = IntentOutputFormat.GENERAL
    elif has_summary_token:
        task_type = IntentTaskType.SUMMARY
        output_format = IntentOutputFormat.GENERAL
    else:
        task_type = IntentTaskType.GENERAL
        output_format = IntentOutputFormat.GENERAL
    focus_topics = [IntentFocusTopic.MAIL_GENERAL]
    if any(token in compact for token in ("수신자", "발신자", "담당자", "문의처", "연락처")):
        focus_topics = [IntentFocusTopic.RECIPIENTS]
    return IntentDecomposition(
        original_query=str(user_message or "").strip(),
        steps=[ExecutionStep.READ_CURRENT_MAIL],
        summary_line_target=5,
        date_filter=DateFilter(mode=DateFilterMode.NONE),
        missing_slots=[],
        task_type=task_type,
        output_format=output_format,
        focus_topics=focus_topics,
        confidence=0.51,
        origin="policy_override",
    )


def _has_current_mail_anchor_text(user_message: str) -> bool:
    """
    decomposition 없이도 현재메일 지시 앵커를 텍스트에서 판별한다.

    Args:
        user_message: 사용자 질의

    Returns:
        현재메일 지시 신호가 있으면 True
    """
    compact = str(user_message or "").replace(" ", "").lower()
    if not compact:
        return False
    anchor_tokens = (
        "현재메일",
        "현재선택메일",
        "현재선택된메일",
        "해당메일",
        "이메일의",
        "이이메일의",
    )
    return any(token in compact for token in anchor_tokens)


def _is_current_mail_decomposition(decomposition: IntentDecomposition | None) -> bool:
    """
    구조화 의도 결과가 현재메일 문맥을 가리키는지 판별한다.

    Args:
        decomposition: 구조화 의도 결과

    Returns:
        현재메일 문맥이면 True
    """
    if decomposition is None:
        return False
    if ExecutionStep.READ_CURRENT_MAIL in decomposition.steps:
        return True
    return False


def _allows_cause_analysis(decomposition: IntentDecomposition | None) -> bool:
    """
    decomposition 기반으로 원인 분석 분기를 허용할지 판단한다.

    Args:
        decomposition: 구조화 의도 결과

    Returns:
        원인 분석 허용 여부
    """
    if decomposition is None:
        return True
    return decomposition.task_type in (IntentTaskType.ANALYSIS, IntentTaskType.SOLUTION, IntentTaskType.GENERAL)


def _allows_solution(decomposition: IntentDecomposition | None) -> bool:
    """
    decomposition 기반으로 해결 분기를 허용할지 판단한다.

    Args:
        decomposition: 구조화 의도 결과

    Returns:
        해결 분기 허용 여부
    """
    if decomposition is None:
        return True
    return decomposition.task_type in (IntentTaskType.SOLUTION, IntentTaskType.ANALYSIS, IntentTaskType.GENERAL)


def _allows_direct_fact(decomposition: IntentDecomposition | None) -> bool:
    """
    decomposition 기반으로 direct fact 분기를 허용할지 판단한다.

    Args:
        decomposition: 구조화 의도 결과

    Returns:
        direct fact 분기 허용 여부
    """
    if decomposition is None:
        return True
    return decomposition.task_type in (
        IntentTaskType.ANALYSIS,
        IntentTaskType.EXTRACTION,
        IntentTaskType.RETRIEVAL,
        IntentTaskType.GENERAL,
    )


def _allows_translation(decomposition: IntentDecomposition | None) -> bool:
    """
    decomposition 기반으로 번역 분기를 허용할지 판단한다.

    Args:
        decomposition: 구조화 의도 결과

    Returns:
        번역 분기 허용 여부
    """
    if decomposition is None:
        return True
    return decomposition.task_type in (
        IntentTaskType.GENERAL,
        IntentTaskType.SUMMARY,
        IntentTaskType.RETRIEVAL,
        IntentTaskType.EXTRACTION,
    )
