from __future__ import annotations

from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    IntentFocusTopic,
    IntentOutputFormat,
    IntentTaskType,
)


def build_text_fallback_decomposition(
    user_message: str,
    has_current_mail_context: bool,
    has_anchor_fn,
    has_direct_fact_entity_signal_fn,
    is_translation_like_request_text_fn,
) -> IntentDecomposition | None:
    """
    LLM 구조분해 실패 시 텍스트 신호 기반 최소 decomposition을 생성한다.
    """
    if not has_current_mail_context and not has_anchor_fn(user_message=user_message):
        return None
    compact = str(user_message or "").replace(" ", "").lower()
    is_translation = is_translation_like_request_text_fn(user_message=user_message)
    has_cause_token = any(token in compact for token in ("원인", "이유", "왜", "문제점"))
    has_solution_token = any(token in compact for token in ("해결", "대응", "조치", "방안", "방법"))
    has_summary_token = any(token in compact for token in ("요약", "정리", "핵심", "주요"))
    has_direct_fact_signal = has_direct_fact_entity_signal_fn(user_message=user_message)
    if is_translation:
        task_type = IntentTaskType.GENERAL
        output_format = IntentOutputFormat.TRANSLATION
    elif has_direct_fact_signal:
        task_type = IntentTaskType.EXTRACTION
        output_format = IntentOutputFormat.GENERAL
    elif has_solution_token and not has_cause_token:
        task_type = IntentTaskType.SOLUTION
        output_format = IntentOutputFormat.ISSUE_ACTION if has_cause_token else IntentOutputFormat.GENERAL
    elif has_cause_token:
        task_type = IntentTaskType.ANALYSIS
        output_format = IntentOutputFormat.ISSUE_ACTION if has_solution_token else IntentOutputFormat.GENERAL
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


def has_current_mail_anchor_text(user_message: str) -> bool:
    """decomposition 없이도 현재메일 지시 앵커를 텍스트에서 판별한다."""
    compact = str(user_message or "").replace(" ", "").lower()
    if not compact:
        return False
    anchor_tokens = ("현재메일", "현재선택메일", "현재선택된메일", "해당메일", "이메일의", "이이메일의")
    return any(token in compact for token in anchor_tokens)


def is_current_mail_decomposition(decomposition: IntentDecomposition | None) -> bool:
    """구조화 의도 결과가 현재메일 문맥을 가리키는지 판별한다."""
    return bool(decomposition is not None and ExecutionStep.READ_CURRENT_MAIL in decomposition.steps)
