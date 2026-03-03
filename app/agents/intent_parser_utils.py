from __future__ import annotations

import json
import re
from typing import Any

from pydantic import ValidationError

from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    IntentFocusTopic,
    IntentOutputFormat,
    IntentTaskType,
    create_default_decomposition,
)
from app.core.intent_rules import (
    build_missing_slots,
    extract_date_filter_fields,
    extract_summary_line_target,
    infer_steps_from_query,
    is_mail_search_query,
    sanitize_user_query,
)

DEFAULT_INTENT_FAST_PATH_MODE = "auto"
DEFAULT_INTENT_MAX_STEPS = 2

STEP_PRIORITY = {
    ExecutionStep.BOOK_MEETING_ROOM: 0,
    ExecutionStep.BOOK_CALENDAR_EVENT: 1,
    ExecutionStep.SEARCH_MEETING_SCHEDULE: 2,
    ExecutionStep.SEARCH_MAILS: 3,
    ExecutionStep.READ_CURRENT_MAIL: 4,
    ExecutionStep.SUMMARIZE_MAIL: 5,
    ExecutionStep.EXTRACT_KEY_FACTS: 6,
    ExecutionStep.EXTRACT_RECIPIENTS: 7,
}
SIMPLE_FAST_PATH_PATTERNS: tuple[tuple[re.Pattern[str], list[ExecutionStep]], ...] = (
    (
        re.compile(r"^현재메일.{0,8}(요약|정리)(해줘|해주세요|해|해줄래)?$"),
        [ExecutionStep.READ_CURRENT_MAIL, ExecutionStep.SUMMARIZE_MAIL],
    ),
    (
        re.compile(r"^현재메일.{0,8}(읽어|보여|보여줘|확인)(줘|해주세요|해줘|해)?$"),
        [ExecutionStep.READ_CURRENT_MAIL],
    ),
)


def build_date_filter(user_message: str) -> DateFilter:
    """공통 규칙 모듈의 추출 결과를 DateFilter 모델로 변환한다."""
    mode, relative, start, end = extract_date_filter_fields(user_message=user_message)
    return DateFilter(
        mode=DateFilterMode(mode),
        relative=relative,
        start=start,
        end=end,
    )


def normalize_steps(raw_steps: list[ExecutionStep], user_message: str) -> list[ExecutionStep]:
    """모델이 반환한 steps를 사용자 입력 근거 기반으로 정규화한다."""
    normalized: list[ExecutionStep] = []
    for step in raw_steps:
        if step not in normalized:
            normalized.append(step)

    inferred_steps = infer_steps_from_query(user_message=user_message)
    step_map = {
        "read_current_mail": ExecutionStep.READ_CURRENT_MAIL,
        "summarize_mail": ExecutionStep.SUMMARIZE_MAIL,
        "extract_key_facts": ExecutionStep.EXTRACT_KEY_FACTS,
        "extract_recipients": ExecutionStep.EXTRACT_RECIPIENTS,
        "search_mails": ExecutionStep.SEARCH_MAILS,
        "search_meeting_schedule": ExecutionStep.SEARCH_MEETING_SCHEDULE,
        "book_meeting_room": ExecutionStep.BOOK_MEETING_ROOM,
        "book_calendar_event": ExecutionStep.BOOK_CALENDAR_EVENT,
    }
    for inferred_step in inferred_steps:
        mapped_step = step_map.get(inferred_step)
        if mapped_step is None:
            continue
        if mapped_step not in normalized:
            normalized.append(mapped_step)

    normalized_text = str(user_message or "").replace(" ", "")
    if is_mail_search_query(text=str(user_message or "").strip()) and "현재메일" not in normalized_text:
        normalized = [
            step
            for step in normalized
            if step
            not in (
                ExecutionStep.READ_CURRENT_MAIL,
                ExecutionStep.EXTRACT_KEY_FACTS,
                ExecutionStep.EXTRACT_RECIPIENTS,
            )
        ]
    return normalized


def build_missing_slots_from_steps(steps: list[ExecutionStep], user_message: str) -> list[str]:
    """예약 의도에 대해 누락된 필수 슬롯 목록을 계산한다."""
    step_values = [step.value for step in steps]
    return build_missing_slots(steps=step_values, user_message=user_message)


def infer_intent_dimensions(
    user_message: str,
    steps: list[ExecutionStep],
) -> tuple[IntentTaskType, IntentOutputFormat, list[IntentFocusTopic], float]:
    """사용자 문장에서 확장 의도 차원(task/output/focus/confidence)을 추론한다."""
    text = str(user_message or "")
    compact = text.replace(" ", "").lower()
    is_solution = any(token in compact for token in ("해결", "해결방법", "대응방안", "개선안", "어떻게해결"))
    is_analysis = any(token in compact for token in ("왜", "원인", "이유", "문제"))
    is_extraction = ("수신자" in compact) or ("받는사람" in compact)
    is_summary = ("요약" in compact) or ("정리" in compact)
    if is_solution:
        task_type = IntentTaskType.SOLUTION
    elif is_analysis:
        task_type = IntentTaskType.ANALYSIS
    elif is_extraction:
        task_type = IntentTaskType.EXTRACTION
    elif ExecutionStep.SEARCH_MAILS in steps:
        task_type = IntentTaskType.RETRIEVAL
    elif is_summary:
        task_type = IntentTaskType.SUMMARY
    else:
        task_type = IntentTaskType.GENERAL

    if re.search(r"\d+\s*줄", text):
        output_format = IntentOutputFormat.LINE_SUMMARY
    elif re.search(r"(자세히|상세)", text):
        output_format = IntentOutputFormat.DETAILED_SUMMARY
    elif "표" in compact:
        output_format = IntentOutputFormat.TABLE
    elif ("핵심문제" in compact or "핵심이슈" in compact) and ("해야할일" in compact or "조치" in compact):
        output_format = IntentOutputFormat.ISSUE_ACTION
    elif ("일정" in compact) and ("담당" in compact) and ("조치" in compact):
        output_format = IntentOutputFormat.SCHEDULE_OWNER_ACTION
    elif task_type == IntentTaskType.SUMMARY:
        output_format = IntentOutputFormat.STRUCTURED_TEMPLATE
    else:
        output_format = IntentOutputFormat.GENERAL

    focus_topics: list[IntentFocusTopic] = []
    if any(token in compact for token in ("수신자", "받는사람", "recipient", "to")):
        focus_topics.append(IntentFocusTopic.RECIPIENTS)
    if any(token in compact for token in ("비용", "예산", "정산")):
        focus_topics.append(IntentFocusTopic.COST)
    if any(token in compact for token in ("기술적이슈", "기술이슈", "오류", "장애", "이슈")):
        focus_topics.append(IntentFocusTopic.TECH_ISSUE)
    if any(token in compact for token in ("일정", "마감", "기한", "딜레이", "지연")):
        focus_topics.append(IntentFocusTopic.SCHEDULE)
    if "ssl" in compact:
        focus_topics.append(IntentFocusTopic.SSL)
    if not focus_topics and ExecutionStep.READ_CURRENT_MAIL in steps:
        focus_topics.append(IntentFocusTopic.MAIL_GENERAL)

    confidence = 0.55
    if task_type in (IntentTaskType.ANALYSIS, IntentTaskType.SOLUTION, IntentTaskType.EXTRACTION):
        confidence = 0.8
    elif task_type in (IntentTaskType.SUMMARY, IntentTaskType.RETRIEVAL):
        confidence = 0.75
    if output_format in (IntentOutputFormat.LINE_SUMMARY, IntentOutputFormat.TABLE):
        confidence = min(0.95, confidence + 0.1)
    return (task_type, output_format, focus_topics, confidence)


def compose_decomposition(
    user_message: str,
    steps: list[ExecutionStep],
    summary_line_target: int,
    date_filter: DateFilter,
) -> IntentDecomposition:
    """공통 필드와 확장 의도 필드를 함께 채워 구조분해 객체를 생성한다."""
    task_type, output_format, focus_topics, confidence = infer_intent_dimensions(
        user_message=user_message,
        steps=steps,
    )
    return IntentDecomposition(
        original_query=user_message,
        steps=steps,
        summary_line_target=summary_line_target,
        date_filter=date_filter,
        missing_slots=build_missing_slots_from_steps(steps=steps, user_message=user_message),
        task_type=task_type,
        output_format=output_format,
        focus_topics=focus_topics,
        confidence=confidence,
    )


def rule_based_decomposition(user_message: str) -> IntentDecomposition:
    """모델 파싱 실패 시 사용할 규칙 기반 최소 구조분해를 생성한다."""
    sanitized_query = sanitize_user_query(user_message=user_message)
    fallback = create_default_decomposition(user_message=sanitized_query)
    steps = normalize_steps(raw_steps=fallback.steps, user_message=sanitized_query)
    return compose_decomposition(
        user_message=sanitized_query,
        steps=steps,
        summary_line_target=extract_summary_line_target(user_message=sanitized_query),
        date_filter=build_date_filter(user_message=sanitized_query),
    )


def serialize_intent_result(result: object) -> str:
    """intent parser 모델 응답 객체를 로그 문자열로 변환한다."""
    if isinstance(result, IntentDecomposition):
        return result.model_dump_json(ensure_ascii=False)
    return str(result)


def normalize_fast_path_mode(raw_mode: str) -> str:
    """intent fast-path 모드 문자열을 허용값으로 정규화한다."""
    mode = str(raw_mode or "").strip().lower()
    if mode in {"auto", "always", "never"}:
        return mode
    return DEFAULT_INTENT_FAST_PATH_MODE


def normalize_max_steps(raw_max_steps: int | str) -> int:
    """step 상한 입력값을 안전한 정수로 정규화한다."""
    try:
        value = int(raw_max_steps)
    except (TypeError, ValueError):
        return DEFAULT_INTENT_MAX_STEPS
    return value if value > 0 else DEFAULT_INTENT_MAX_STEPS


def limit_execution_steps(steps: list[ExecutionStep], max_steps: int) -> list[ExecutionStep]:
    """step 목록을 우선순위 기준으로 정렬한 뒤 상한 개수로 제한한다."""
    if not steps:
        return []
    if len(steps) <= max_steps:
        return steps
    indexed_steps = list(enumerate(steps))
    ranked = sorted(
        indexed_steps,
        key=lambda item: (
            STEP_PRIORITY.get(item[1], 999),
            item[0],
        ),
    )
    return [step for _, step in ranked[:max_steps]]


def apply_step_limit_to_decomposition(
    decomposition: IntentDecomposition,
    max_steps: int,
) -> IntentDecomposition:
    """구조분해 결과에 step 상한을 적용해 최종 객체를 재구성한다."""
    required_steps = infer_required_steps_from_query(user_message=decomposition.original_query)
    effective_max_steps = max(max_steps, len(required_steps))
    limited_steps = limit_execution_steps_with_required(
        steps=decomposition.steps,
        max_steps=effective_max_steps,
        required_steps=required_steps,
    )
    rebuilt = compose_decomposition(
        user_message=decomposition.original_query,
        steps=limited_steps,
        summary_line_target=decomposition.summary_line_target,
        date_filter=decomposition.date_filter,
    )
    if decomposition.focus_topics:
        rebuilt.focus_topics = decomposition.focus_topics
    rebuilt.task_type = decomposition.task_type
    rebuilt.output_format = decomposition.output_format
    rebuilt.confidence = decomposition.confidence
    return rebuilt


def try_simple_fast_path(user_message: str, fast_path_mode: str) -> IntentDecomposition | None:
    """fast-path 모드에 따라 규칙 기반 사전 분해를 시도한다."""
    if fast_path_mode == "never":
        return None
    if fast_path_mode == "always":
        return rule_based_decomposition(user_message=user_message)
    simple = build_simple_fast_path_decomposition(user_message=user_message)
    if simple is not None:
        return simple
    if is_rule_fast_path_candidate(user_message=user_message):
        return rule_based_decomposition(user_message=user_message)
    return None


def is_rule_fast_path_candidate(user_message: str) -> bool:
    """auto 모드에서 Ollama 호출을 생략해도 되는 fast-path 후보인지 판별한다."""
    inferred_steps = infer_steps_from_query(user_message=user_message)
    return bool(inferred_steps)


def build_simple_fast_path_decomposition(user_message: str) -> IntentDecomposition | None:
    """초단순 패턴 질의에 대해서만 fast-path 구조분해를 생성한다."""
    compact = re.sub(r"\s+", "", user_message)
    for pattern, steps in SIMPLE_FAST_PATH_PATTERNS:
        if not pattern.fullmatch(compact):
            continue
        return compose_decomposition(
            user_message=user_message,
            steps=steps,
            summary_line_target=extract_summary_line_target(user_message=user_message),
            date_filter=build_date_filter(user_message=user_message),
        )
    return None


def is_valid_decomposition(decomposition: IntentDecomposition, user_message: str) -> bool:
    """모델 구조분해 결과가 최소 품질 기준을 만족하는지 검증한다."""
    if not decomposition.steps:
        return False
    required_steps = infer_required_steps_from_query(user_message=user_message)
    return required_steps.issubset(set(decomposition.steps))


def infer_required_steps_from_query(user_message: str) -> set[ExecutionStep]:
    """사용자 질의의 핵심 키워드에서 필수 step 집합을 계산한다."""
    text = str(user_message or "").replace(" ", "")
    required: set[ExecutionStep] = set()
    if "현재메일" in text:
        required.add(ExecutionStep.READ_CURRENT_MAIL)
    if is_mail_search_query(text=str(user_message or "").strip()):
        required.add(ExecutionStep.SEARCH_MAILS)
    if "수신자" in text or "받는" in text:
        required.add(ExecutionStep.EXTRACT_RECIPIENTS)
    if "중요" in text or "핵심" in text or "주요" in text or "키워드" in text or "할일" in text or "액션아이템" in text:
        required.add(ExecutionStep.EXTRACT_KEY_FACTS)
    if (
        "왜" in text
        or "원인" in text
        or "이유" in text
        or "문제" in text
        or "해결" in text
        or "대응" in text
        or "방안" in text
    ):
        required.add(ExecutionStep.SUMMARIZE_MAIL)
        required.add(ExecutionStep.EXTRACT_KEY_FACTS)
    if "요약" in text or "정리" in text or "보고서" in text:
        required.add(ExecutionStep.SUMMARIZE_MAIL)
    if "예약" in text or "잡아" in text:
        required.add(ExecutionStep.BOOK_MEETING_ROOM)
    if "일정" in text and ("등록" in text or "추가" in text or "생성" in text) and "회의실" not in text:
        required.add(ExecutionStep.BOOK_CALENDAR_EVENT)
    return required


def limit_execution_steps_with_required(
    steps: list[ExecutionStep],
    max_steps: int,
    required_steps: set[ExecutionStep],
) -> list[ExecutionStep]:
    """step 상한 적용 시 required step이 누락되지 않도록 보정한다."""
    if not steps:
        return []
    normalized_required = [step for step in steps if step in required_steps]
    if len(steps) <= max_steps:
        return steps

    limited = limit_execution_steps(steps=steps, max_steps=max_steps)
    for required in normalized_required:
        if required in limited:
            continue
        replace_index = find_replaceable_index(limited=limited, required_steps=required_steps)
        if replace_index is None:
            limited.append(required)
            continue
        limited[replace_index] = required
    return dedupe_steps_preserve_order(steps=limited)


def find_replaceable_index(
    limited: list[ExecutionStep],
    required_steps: set[ExecutionStep],
) -> int | None:
    """제한된 step 목록에서 required를 대체 삽입할 인덱스를 찾는다."""
    candidates = [
        (index, STEP_PRIORITY.get(step, 999))
        for index, step in enumerate(limited)
        if step not in required_steps
    ]
    if not candidates:
        return None
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0][0]


def dedupe_steps_preserve_order(steps: list[ExecutionStep]) -> list[ExecutionStep]:
    """step 목록에서 순서를 유지한 채 중복을 제거한다."""
    deduped: list[ExecutionStep] = []
    for step in steps:
        if step in deduped:
            continue
        deduped.append(step)
    return deduped


def parse_intent_json_from_text(text: str) -> IntentDecomposition | None:
    """코드블록/평문으로 감싸진 JSON 문자열을 IntentDecomposition으로 파싱한다."""
    payload_text = str(text or "").strip()
    if payload_text.startswith("```"):
        payload_text = re.sub(r"^```(?:json)?\s*", "", payload_text, flags=re.IGNORECASE)
        payload_text = re.sub(r"\s*```$", "", payload_text)
    try:
        payload = json.loads(payload_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return None
    try:
        return IntentDecomposition.model_validate(payload)
    except ValidationError:
        return None
