from __future__ import annotations

from functools import lru_cache
from typing import Sequence

from langchain_core.messages import BaseMessage, HumanMessage

from app.agents.intent_parser import get_intent_parser
from app.core.intent_rules import infer_steps_from_query, is_code_review_query, is_mail_summary_skill_query
from app.agents.intent_schema import (
    ExecutionStep,
    IntentDecomposition,
    IntentOutputFormat,
    IntentTaskType,
    create_default_decomposition,
    decomposition_to_context_text,
)
from app.core.logging_config import get_logger
from app.services.current_mail_intent_policy import (
    is_current_mail_direct_fact_request,
    is_current_mail_translation_request,
)
from app.services.intent_decomposition_service import (
    build_intent_namespace_kwargs,
    is_current_mail_scope_label,
    parse_intent_decomposition_safely,
)
from app.middleware.intent_routing_policy import (
    is_calendar_event_hil_payload_request,
    is_composite_mail_retrieval_request,
    is_explicit_todo_registration_request,
    is_mail_subagents_enabled,
    is_meeting_room_hil_payload_request,
    is_recipient_todo_summary_request,
)

INTENT_CONTEXT_PREFIX = "구조분해 결과:"
INTENT_SYSTEM_CONTEXT_PREFIX = "의도 라우팅 컨텍스트:"
logger = get_logger(__name__)
FAILED_DELIVERY_TOKENS: tuple[str, ...] = (
    "수신안",
    "수신 안",
    "수신실패",
    "수신 실패",
    "미수신",
    "차단",
    "반송",
    "ndr",
    "undeliverable",
    "bounce",
    "bounced",
    "blocked",
)
ADDRESS_QUERY_TOKENS: tuple[str, ...] = ("메일주소", "메일 주소", "이메일", "주소", "도메인", "from")


def find_last_human_message(messages: Sequence[BaseMessage]) -> tuple[int, HumanMessage] | None:
    """
    메시지 목록에서 마지막 HumanMessage를 찾는다.

    Args:
        messages: 모델 호출 직전 메시지 목록

    Returns:
        (인덱스, HumanMessage) 튜플 또는 None
    """
    for index in range(len(messages) - 1, -1, -1):
        message = messages[index]
        if isinstance(message, HumanMessage):
            return (index, message)
    return None


def normalize_message_text(content: object) -> str:
    """
    메시지 content를 문자열로 정규화한다.

    Args:
        content: 메시지 content 원본 값

    Returns:
        정규화된 문자열
    """
    if isinstance(content, str):
        return content.strip()
    return str(content or "").strip()


def is_intent_context_injected(message_text: str) -> bool:
    """
    사용자 메시지에 구조분해 컨텍스트가 이미 주입되었는지 확인한다.

    Args:
        message_text: 사용자 메시지 텍스트

    Returns:
        이미 주입된 경우 True
    """
    return message_text.startswith(INTENT_CONTEXT_PREFIX)


def compose_intent_augmented_text(user_message: str) -> str:
    """
    사용자 입력을 의도 구조분해 컨텍스트와 결합한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        구조분해 컨텍스트 + 원본 입력 문자열
    """
    original_user_message, decomposition_json, context_text, routing_instruction = _compose_intent_context_payload(
        user_message=user_message
    )
    logger.info("미들웨어 의도 구조분해 결과(JSON): %s", decomposition_json)
    return f"{context_text}\n{routing_instruction}\n\n원본 사용자 입력:\n{original_user_message.strip()}"


def compose_intent_system_context(user_message: str) -> str:
    """
    사용자 입력을 변경하지 않고 모델에 주입할 system 컨텍스트를 생성한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        system 메시지로 주입할 의도 컨텍스트 문자열
    """
    original_user_message, decomposition_json, context_text, routing_instruction = _compose_intent_context_payload(
        user_message=user_message
    )
    logger.info("미들웨어 의도 구조분해 결과(JSON): %s", decomposition_json)
    return (
        f"{INTENT_SYSTEM_CONTEXT_PREFIX}\n"
        f"{context_text}\n"
        f"{routing_instruction}\n\n"
        f"원본 사용자 입력:\n{original_user_message.strip()}"
    )


@lru_cache(maxsize=256)
def _compose_intent_context_payload(user_message: str) -> tuple[str, str, str, str]:
    """
    동일 입력의 의도 컨텍스트 조합 결과를 캐시해 재파싱을 줄인다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        (원본 사용자 입력, decomposition_json, context_text, routing_instruction)
    """
    scope_label, original_user_message = _split_scope_instruction(user_message=user_message)
    decomposition = _parse_intent_with_namespace(
        user_message=original_user_message,
        scope_label=scope_label,
    )
    decomposition = _apply_current_mail_policy_overrides(
        decomposition=decomposition,
        original_user_message=original_user_message,
        scope_label=scope_label,
    )
    decomposition_json = decomposition.model_dump_json(ensure_ascii=False)
    context_text = decomposition_to_context_text(decomposition=decomposition)
    routing_instruction = _build_routing_instruction(
        decomposition=decomposition,
        original_user_message=original_user_message,
        scope_label=scope_label,
    )
    return (original_user_message, decomposition_json, context_text, routing_instruction)


def clear_intent_context_payload_cache() -> None:
    """
    테스트/운영 제어를 위해 intent 컨텍스트 조합 캐시를 초기화한다.
    """
    _compose_intent_context_payload.cache_clear()


def _build_routing_instruction(
    decomposition: IntentDecomposition,
    original_user_message: str,
    scope_label: str,
) -> str:
    """
    구조분해 결과 기반의 실행 라우팅 지시 문구를 생성한다.

    Args:
        decomposition: 의도 구조분해 결과

    Returns:
        모델 입력에 주입할 라우팅 지시 문자열
    """
    lines = ["라우팅 지시:"]
    if decomposition.task_type in (IntentTaskType.ANALYSIS, IntentTaskType.SOLUTION):
        lines.append("- 반드시 현재메일 근거를 먼저 확인한 뒤 답변한다.")
    if decomposition.output_format == IntentOutputFormat.TABLE:
        lines.append("- 응답을 markdown 표로 작성한다.")
    if decomposition.output_format == IntentOutputFormat.LINE_SUMMARY:
        lines.append(f"- summary_line_target={decomposition.summary_line_target} 줄을 정확히 맞춘다.")
    if scope_label:
        lines.append(f"- 범위 지시: {scope_label}")
    has_current_mail_scope = is_current_mail_scope_label(scope_label=scope_label)
    is_direct_fact_request = is_current_mail_direct_fact_request(
        user_message=original_user_message,
        has_current_mail_context=has_current_mail_scope,
        decomposition=decomposition,
    )
    is_translation_request = is_current_mail_translation_request(
        user_message=original_user_message,
        has_current_mail_context=has_current_mail_scope,
        decomposition=decomposition,
    )
    if is_direct_fact_request:
        lines.append("- 특정 항목(메일주소/도메인/주체) 질문은 해당 값을 먼저 1~3개로 직접 답한다.")
        lines.append("- 불필요한 원인/영향/대응 섹션 확장은 금지하고, 필요 시 근거 1줄만 덧붙인다.")
        if _is_failed_delivery_address_query(user_message=original_user_message):
            lines.append("- `수신 실패/미수신/차단/반송` + 주소 질의는 실패가 명시된 주소만 답한다. 전체 수신자 목록 나열은 금지한다.")
            lines.append("- 실패 주소를 특정할 수 없으면 `본문에서 특정 주소를 확인할 수 없습니다`라고 답한다.")
    if is_translation_request:
        lines.append("- 번역 요청은 요약 대신 원문 의미를 유지한 전체 번역문을 우선 제공한다.")
        lines.append("- 핵심 bullet/조치 섹션으로 재구성하지 말고 문단 단위 번역을 유지한다.")
    if decomposition.task_type == IntentTaskType.ANALYSIS:
        if not is_direct_fact_request:
            lines.append("- 원인/영향/대응 순서로 간결하게 정리한다.")
    if decomposition.task_type == IntentTaskType.SOLUTION:
        lines.append("- 가능한 원인/점검 순서/즉시 조치 순서로 제시한다.")
    is_meeting_room_hil_payload = is_meeting_room_hil_payload_request(decomposition=decomposition)
    is_calendar_event_hil_payload = is_calendar_event_hil_payload_request(decomposition=decomposition)
    is_explicit_todo_registration = is_explicit_todo_registration_request(decomposition=decomposition)
    if (
        decomposition.confidence < 0.6
        and not is_explicit_todo_registration
        and not is_meeting_room_hil_payload
        and not is_calendar_event_hil_payload
    ):
        lines.append("- 의도가 모호하면 답변 전에 한 문장으로 확인 질문을 먼저 한다.")
    if is_meeting_room_hil_payload:
        lines.append("- 회의실 예약 HIL 페이로드이므로 추가 질문 없이 book_meeting_room 도구를 실행한다.")
        lines.append("- 전달된 슬롯(date/start_time/end_time/attendee_count/building/floor/room_name)을 그대로 사용한다.")
    if is_calendar_event_hil_payload:
        lines.append("- 일정 등록 HIL 페이로드이므로 추가 질문 없이 create_outlook_calendar_event 도구를 실행한다.")
        lines.append("- 전달된 슬롯(subject/date/start_time/end_time/attendees/body)을 그대로 사용한다.")
    if is_explicit_todo_registration:
        lines.append("- ToDo 등록 요청은 추가 질문 없이 create_outlook_todo 도구를 실행한다.")
    if is_recipient_todo_summary_request(decomposition=decomposition):
        lines.append("- 수신자 todo/마감기한 요약 요청은 표/요약만 수행하고 실행 툴(create_outlook_todo)은 호출하지 않는다.")
    if is_mail_subagents_enabled() and is_composite_mail_retrieval_request(decomposition=decomposition):
        lines.append("- 복합 메일 조회 질의이므로 `mail-retrieval-summary-agent`에 위임해 주요 내용 digest를 먼저 수집한다.")
        lines.append("- 기술 이슈 축은 `mail-tech-issue-agent`에 위임해 기술 이슈 후보를 별도로 수집한다.")
        lines.append("- 최종 응답은 `주요 내용`/`기술 이슈`/`근거 메일` 순서로 통합한다.")
    return "\n".join(lines)


def _is_failed_delivery_address_query(user_message: str) -> bool:
    """
    수신 실패 주소를 특정하려는 직접값 질의인지 판별한다.

    Args:
        user_message: scope prefix 제거된 사용자 질의

    Returns:
        실패/차단 맥락 + 주소 엔터티 질의면 True
    """
    normalized = str(user_message or "").strip().lower()
    if not normalized:
        return False
    has_failed_delivery_signal = any(token in normalized for token in FAILED_DELIVERY_TOKENS)
    if not has_failed_delivery_signal:
        return False
    has_address_signal = any(token in normalized for token in ADDRESS_QUERY_TOKENS)
    return has_address_signal


def _split_scope_instruction(user_message: str) -> tuple[str, str]:
    """
    scope prefix가 주입된 입력에서 범위 라벨과 원본 질의를 분리한다.

    Args:
        user_message: 사용자 입력(주입 prefix 포함 가능)

    Returns:
        (범위 라벨, 원본 질의)
    """
    text = str(user_message or "").strip()
    if not text.startswith("[질의 범위]"):
        return ("", text)
    lines = text.splitlines()
    if not lines:
        return ("", "")
    scope_label = lines[0].strip()
    original = "\n".join(lines[1:]).strip()
    return (scope_label, original or text)


def _parse_intent_with_namespace(user_message: str, scope_label: str) -> IntentDecomposition:
    """
    scope 라벨 기반 namespace를 포함해 intent parser를 호출한다.

    Args:
        user_message: scope prefix 제거된 사용자 질의
        scope_label: scope 라벨 문자열

    Returns:
        intent 구조분해 결과
    """
    parse_kwargs = build_intent_namespace_kwargs(scope_label=scope_label)
    parsed = parse_intent_decomposition_safely(
        user_message=user_message,
        parser_factory=get_intent_parser,
        has_selected_mail=bool(parse_kwargs["has_selected_mail"]),
        selected_message_id_exists=bool(parse_kwargs["selected_message_id_exists"]),
    )
    if parsed is not None:
        return parsed
    return parse_intent_decomposition_safely(
        user_message=user_message,
        parser_factory=get_intent_parser,
    ) or create_default_decomposition(user_message=user_message)


def _apply_current_mail_policy_overrides(
    decomposition: IntentDecomposition,
    original_user_message: str,
    scope_label: str,
) -> IntentDecomposition:
    """
    현재메일 범위 질의에서 필요한 최소 정책 보정을 적용한다.

    Args:
        decomposition: 파싱된 의도 구조분해
        original_user_message: scope prefix 제거 사용자 질의
        scope_label: 범위 라벨 문자열

    Returns:
        보정이 반영된 의도 구조분해
    """
    current_mail_focused = _is_current_mail_focused_query(
        user_message=original_user_message,
        scope_label=scope_label,
    )
    if not current_mail_focused:
        return decomposition

    updated = decomposition
    changed = False

    if _should_drop_search_step_in_current_mail(
        user_message=original_user_message,
        decomposition=updated,
    ):
        pruned_steps = [step for step in updated.steps if step != ExecutionStep.SEARCH_MAILS]
        if pruned_steps != list(updated.steps):
            updated = updated.model_copy(update={"steps": pruned_steps})
            changed = True

    if (
        updated.task_type == IntentTaskType.RETRIEVAL
        and not updated.steps
    ):
        updated = updated.model_copy(update={"steps": [ExecutionStep.READ_CURRENT_MAIL]})
        changed = True

    if _should_override_task_type_to_extraction(
        user_message=original_user_message,
        decomposition=updated,
    ):
        updated = updated.model_copy(update={"task_type": IntentTaskType.EXTRACTION})
        changed = True

    if _should_override_output_format_to_general(
        user_message=original_user_message,
        decomposition=updated,
    ):
        updated = updated.model_copy(update={"output_format": IntentOutputFormat.GENERAL})
        changed = True

    if changed and updated.origin != "policy_override":
        updated = updated.model_copy(update={"origin": "policy_override"})
    return updated


def _is_current_mail_focused_query(user_message: str, scope_label: str) -> bool:
    """
    현재메일 고정 문맥 질의인지 판별한다.

    Args:
        user_message: scope prefix 제거 사용자 질의
        scope_label: 범위 라벨 문자열

    Returns:
        현재메일 고정 질의면 True
    """
    if is_current_mail_scope_label(scope_label=scope_label):
        return True
    compact = str(user_message or "").replace(" ", "")
    anchors = ("현재메일", "현재선택메일", "이이메일", "이메일에서", "이메일의")
    return any(token in compact for token in anchors)


def _should_drop_search_step_in_current_mail(
    user_message: str,
    decomposition: IntentDecomposition,
) -> bool:
    """
    현재메일 문맥에서 불필요한 search_mails step 제거 여부를 판단한다.

    Args:
        user_message: 사용자 질의
        decomposition: 구조분해 결과

    Returns:
        search_mails 제거 대상이면 True
    """
    if ExecutionStep.SEARCH_MAILS not in decomposition.steps:
        return False
    compact = str(user_message or "").replace(" ", "")
    keep_search_tokens = ("다른메일", "관련된다른", "검색", "조회", "찾아")
    if any(token in compact for token in keep_search_tokens):
        return False
    return True


def _should_override_output_format_to_general(
    user_message: str,
    decomposition: IntentDecomposition,
) -> bool:
    """
    현재메일 자연어 질의의 structured_template을 general로 보정할지 판단한다.

    Args:
        user_message: 사용자 질의
        decomposition: 구조분해 결과

    Returns:
        output_format general 보정 대상이면 True
    """
    if decomposition.output_format != IntentOutputFormat.STRUCTURED_TEMPLATE:
        return False
    if is_mail_summary_skill_query(user_message=user_message):
        return False
    return True


def _should_override_task_type_to_extraction(
    user_message: str,
    decomposition: IntentDecomposition,
) -> bool:
    """
    구조 추출형 현재메일 질의를 analysis -> extraction으로 보정할지 판단한다.

    Args:
        user_message: 사용자 질의
        decomposition: 구조분해 결과

    Returns:
        task_type extraction 보정 대상이면 True
    """
    if decomposition.task_type != IntentTaskType.ANALYSIS:
        return False
    compact = str(user_message or "").replace(" ", "")
    analysis_tokens = ("원인", "이유", "왜", "문제", "이슈", "영향", "대응", "해결", "방안")
    if any(token in compact for token in analysis_tokens):
        return False
    steps = list(decomposition.steps)
    has_extract = ExecutionStep.EXTRACT_KEY_FACTS in steps
    has_summary = ExecutionStep.SUMMARIZE_MAIL in steps
    return has_extract and not has_summary


def should_inject_intent_context(user_message: str) -> bool:
    """
    사용자 질의에 구조분해 컨텍스트 주입이 필요한지 판별한다.

    Args:
        user_message: 원본 사용자 질의

    Returns:
        주입이 필요하면 True
    """
    if is_code_review_query(user_message=user_message):
        return False
    scope_label, original_user_message = _split_scope_instruction(user_message=user_message)
    if is_current_mail_scope_label(scope_label=scope_label):
        return True
    parsed = parse_intent_decomposition_safely(
        user_message=original_user_message or user_message,
        parser_factory=get_intent_parser,
    )
    if parsed is None:
        fallback_steps_when_parse_failed = infer_steps_from_query(user_message=user_message)
        if fallback_steps_when_parse_failed == ["search_mails"]:
            return False
        return True
    steps = [step.value for step in parsed.steps]
    # 단일 메일조회는 규칙 분기가 안정적이라 컨텍스트 주입을 생략해 토큰/지연을 줄인다.
    if steps == ["search_mails"]:
        return False
    fallback_steps = infer_steps_from_query(user_message=user_message)
    if fallback_steps == ["search_mails"]:
        return False
    return True
