from __future__ import annotations

from app.agents.intent_schema import IntentDecomposition, IntentFocusTopic, IntentOutputFormat, IntentTaskType
from app.services.intent_decomposition_service import parse_intent_decomposition_safely


def should_apply_current_mail_grounded_safe_guard(
    user_message: str,
    decomposition: IntentDecomposition | None = None,
) -> bool:
    """
    현재메일 저근거 안전가드를 적용할지 공통 정책으로 판별한다.

    Args:
        user_message: 사용자 입력 원문
        decomposition: 구조화 의도 결과(있으면 우선 사용)

    Returns:
        안전가드 적용 대상이면 True
    """
    resolved = decomposition or parse_intent_decomposition_safely(user_message=user_message)
    if resolved is None:
        return False
    if resolved.task_type == IntentTaskType.ACTION:
        return False
    if resolved.output_format == IntentOutputFormat.TRANSLATION:
        return False
    if resolved.task_type == IntentTaskType.SUMMARY:
        high_risk_topics = {IntentFocusTopic.TECH_ISSUE, IntentFocusTopic.COST, IntentFocusTopic.RECIPIENTS}
        if not high_risk_topics.intersection(set(resolved.focus_topics)):
            return False
    return resolved.task_type in (
        IntentTaskType.ANALYSIS,
        IntentTaskType.SOLUTION,
        IntentTaskType.SUMMARY,
        IntentTaskType.EXTRACTION,
        IntentTaskType.RETRIEVAL,
        IntentTaskType.GENERAL,
    )


def render_current_mail_grounded_safe_message(user_message: str, summary_text: str) -> str:
    """
    현재메일 저근거 상황에서 의도 정합 안전응답 문구를 생성한다.

    Args:
        user_message: 사용자 입력 원문
        summary_text: 현재메일 요약 텍스트

    Returns:
        의도 기반 안전응답
    """
    safe_summary = str(summary_text or "").strip()[:240]
    return (
        f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
        "질문과 직접 관련된 세부 항목은 현재 근거만으로 확인할 수 없습니다."
    )
