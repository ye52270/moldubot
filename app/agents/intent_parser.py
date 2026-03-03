from __future__ import annotations

import json
import os
import re
from collections import OrderedDict
from functools import lru_cache
from typing import Any

from pydantic import ValidationError

from app.core.logging_config import get_logger, is_prompt_trace_enabled
from app.core.intent_rules import (
    build_missing_slots,
    extract_date_filter_fields,
    extract_summary_line_target,
    infer_steps_from_query,
    is_mail_search_query,
    sanitize_user_query,
)
from app.agents.intent_schema import (
    DateFilter,
    DateFilterMode,
    ExecutionStep,
    IntentDecomposition,
    create_default_decomposition,
)

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_EXAONE_MODEL = "exaone3.5:2.4b"
DEFAULT_INTENT_FAST_PATH_MODE = "auto"
DEFAULT_INTENT_MAX_STEPS = 2
INTENT_PARSE_CACHE_SIZE = 128

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

logger = get_logger(__name__)


def _build_date_filter(user_message: str) -> DateFilter:
    """
    공통 규칙 모듈의 추출 결과를 DateFilter 모델로 변환한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        구조화된 날짜 필터
    """
    mode, relative, start, end = extract_date_filter_fields(user_message=user_message)
    return DateFilter(
        mode=DateFilterMode(mode),
        relative=relative,
        start=start,
        end=end,
    )


def _normalize_steps(raw_steps: list[ExecutionStep], user_message: str) -> list[ExecutionStep]:
    """
    모델이 반환한 steps를 사용자 입력 근거 기반으로 정규화한다.

    Args:
        raw_steps: 모델이 반환한 실행 단계 목록
        user_message: 원본 사용자 입력

    Returns:
        정규화된 실행 단계 목록
    """
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


def _build_missing_slots(steps: list[ExecutionStep], user_message: str) -> list[str]:
    """
    예약 의도에 대해 누락된 필수 슬롯 목록을 계산한다.

    Args:
        steps: 정규화된 실행 단계 목록
        user_message: 원본 사용자 입력

    Returns:
        누락된 슬롯 목록
    """
    step_values = [step.value for step in steps]
    return build_missing_slots(steps=step_values, user_message=user_message)


def _rule_based_decomposition(user_message: str) -> IntentDecomposition:
    """
    모델 파싱 실패 시 사용할 규칙 기반 최소 구조분해를 생성한다.

    Args:
        user_message: 원본 사용자 입력

    Returns:
        규칙 기반 구조분해 결과
    """
    sanitized_query = sanitize_user_query(user_message=user_message)
    fallback = create_default_decomposition(user_message=sanitized_query)
    steps = _normalize_steps(raw_steps=fallback.steps, user_message=sanitized_query)
    return IntentDecomposition(
        original_query=sanitized_query,
        steps=steps,
        summary_line_target=extract_summary_line_target(user_message=sanitized_query),
        date_filter=_build_date_filter(user_message=sanitized_query),
        missing_slots=_build_missing_slots(steps=steps, user_message=sanitized_query),
    )


class ExaoneIntentParser:
    """
    Ollama Exaone 모델로 최소 구조분해를 수행하는 파서 클래스.
    """

    def __init__(
        self,
        model_name: str,
        base_url: str,
        temperature: float = 0.0,
        fast_path_mode: str = DEFAULT_INTENT_FAST_PATH_MODE,
        max_steps: int = DEFAULT_INTENT_MAX_STEPS,
    ) -> None:
        """
        Exaone 파서 인스턴스를 초기화한다.

        Args:
            model_name: Ollama 모델 이름
            base_url: Ollama 서버 URL
            temperature: 생성 온도
            fast_path_mode: 규칙 fast-path 모드(`auto`, `always`, `never`)
            max_steps: 최종 steps 최대 개수
        """
        self._model_name = model_name
        self._base_url = base_url
        self._temperature = temperature
        self._fast_path_mode = _normalize_fast_path_mode(raw_mode=fast_path_mode)
        self._max_steps = _normalize_max_steps(raw_max_steps=max_steps)
        self._structured_model: Any = None
        self._parse_cache: OrderedDict[str, IntentDecomposition] = OrderedDict()

    def parse(self, user_message: str) -> IntentDecomposition:
        """
        사용자 문장을 최소 의도 구조분해 형태로 변환한다.

        Args:
            user_message: 원본 사용자 입력

        Returns:
            최소 구조분해 결과
        """
        sanitized_query = sanitize_user_query(user_message=user_message)
        if not sanitized_query:
            logger.info("의도 구조분해 입력이 비어 기본 분해를 반환합니다.")
            return create_default_decomposition(user_message=user_message)

        cached = self._read_cached_decomposition(user_message=sanitized_query)
        if cached is not None:
            logger.info("intent parse cache hit")
            return _apply_step_limit_to_decomposition(
                decomposition=cached,
                max_steps=self._max_steps,
            )

        fast_path_result = _try_simple_fast_path(
            user_message=sanitized_query,
            fast_path_mode=self._fast_path_mode,
        )
        if fast_path_result is not None:
            logger.info("intent fast-path 적용: mode=%s", self._fast_path_mode)
            final_decomposition = _apply_step_limit_to_decomposition(
                decomposition=fast_path_result,
                max_steps=self._max_steps,
            )
            self._write_cached_decomposition(user_message=sanitized_query, decomposition=final_decomposition)
            return final_decomposition

        prompt = self._build_prompt(user_message=sanitized_query)
        parsed = self._invoke_ollama_structured(prompt=prompt)
        if parsed is None:
            logger.info("Ollama 구조분해 실패로 규칙 기반 분해로 전환합니다.")
            fallback = _apply_step_limit_to_decomposition(
                decomposition=_rule_based_decomposition(user_message=sanitized_query),
                max_steps=self._max_steps,
            )
            self._write_cached_decomposition(user_message=sanitized_query, decomposition=fallback)
            return fallback

        normalized_steps = _normalize_steps(raw_steps=parsed.steps, user_message=sanitized_query)
        limited_steps = _limit_execution_steps(steps=normalized_steps, max_steps=self._max_steps)
        decomposition = IntentDecomposition(
            original_query=sanitized_query,
            steps=limited_steps,
            summary_line_target=extract_summary_line_target(user_message=sanitized_query),
            date_filter=_build_date_filter(user_message=sanitized_query),
            missing_slots=_build_missing_slots(steps=limited_steps, user_message=sanitized_query),
        )
        if not _is_valid_decomposition(decomposition=decomposition, user_message=sanitized_query):
            logger.warning("Ollama 구조분해 품질 검증 실패로 규칙 기반 분해로 전환합니다.")
            fallback = _apply_step_limit_to_decomposition(
                decomposition=_rule_based_decomposition(user_message=sanitized_query),
                max_steps=self._max_steps,
            )
            self._write_cached_decomposition(user_message=sanitized_query, decomposition=fallback)
            return fallback
        logger.info("Ollama 구조분해 성공: steps=%s", [step.value for step in decomposition.steps])
        self._write_cached_decomposition(user_message=sanitized_query, decomposition=decomposition)
        return decomposition

    def _read_cached_decomposition(self, user_message: str) -> IntentDecomposition | None:
        """
        동일 질의에 대한 구조분해 캐시를 조회한다.

        Args:
            user_message: 정규화된 사용자 질의

        Returns:
            캐시된 구조분해 결과 또는 None
        """
        cached = self._parse_cache.get(user_message)
        if cached is None:
            return None
        self._parse_cache.move_to_end(user_message)
        return cached.model_copy(deep=True)

    def _write_cached_decomposition(self, user_message: str, decomposition: IntentDecomposition) -> None:
        """
        구조분해 결과를 LRU 캐시에 저장한다.

        Args:
            user_message: 정규화된 사용자 질의
            decomposition: 저장할 구조분해 결과
        """
        self._parse_cache[user_message] = decomposition.model_copy(deep=True)
        self._parse_cache.move_to_end(user_message)
        while len(self._parse_cache) > INTENT_PARSE_CACHE_SIZE:
            self._parse_cache.popitem(last=False)

    def _get_structured_model(self) -> Any:
        """
        Ollama structured output 모델 인스턴스를 재사용한다.

        Returns:
            `IntentDecomposition` structured model
        """
        if self._structured_model is not None:
            return self._structured_model
        from langchain_ollama import ChatOllama

        model = ChatOllama(
            model=self._model_name,
            base_url=self._base_url,
            temperature=self._temperature,
        )
        self._structured_model = model.with_structured_output(IntentDecomposition)
        return self._structured_model

    def _build_prompt(self, user_message: str) -> str:
        """
        Exaone 최소 구조분해 프롬프트를 생성한다.

        Args:
            user_message: 원본 사용자 입력

        Returns:
            구조분해 프롬프트
        """
        return (
            "너는 한국어 업무 요청을 최소 JSON으로 구조분해하는 라우터다.\n"
            "절대 규칙:\n"
            "1) JSON 객체 1개만 출력한다. 설명/코드블록/주석 금지.\n"
            "2) 키 이름은 스키마와 정확히 일치해야 한다.\n"
            "3) 입력에 없는 정보는 추측하지 않는다.\n"
            "4) steps는 허용값에서만 선택한다.\n"
            "5) summary_line_target은 'N줄'일 때만 N, 없으면 5.\n"
            "6) 날짜 표현이 없으면 date_filter.mode는 none.\n"
            '   "N월분", "N분기분", "상반기분", "하반기분" 같은 표현은 청구/정산 기간을 의미하며 메일 수신 날짜가 아니므로 date_filter는 반드시 none으로 한다.\n'
            '   날짜 필터는 "이번 주", "어제", "지난달에 받은", "1월에 온"처럼 명시적으로 수신 시점을 가리키는 표현에만 적용한다.\n'
            "7) 회의예약이 있으면 missing_slots에 date,start_time,end_time,attendee_count 누락값을 채운다.\n\n"
            "허용 steps: read_current_mail, summarize_mail, extract_key_facts, extract_recipients, "
            "search_mails, search_meeting_schedule, book_meeting_room, book_calendar_event\n\n"
            "출력 스키마:\n"
            "{\n"
            '  "original_query": "",\n'
            '  "steps": [],\n'
            '  "summary_line_target": 5,\n'
            '  "date_filter": {"mode":"none|relative|absolute","relative":"","start":"","end":""},\n'
            '  "missing_slots": []\n'
            "}\n\n"
            f"사용자 입력: {user_message}\n"
            "출력: JSON 객체 1개"
        )

    def _invoke_ollama_structured(self, prompt: str) -> IntentDecomposition | None:
        """
        Ollama structured output 호출로 구조분해 결과를 얻는다.

        Args:
            prompt: 구조분해 프롬프트

        Returns:
            파싱 성공 시 IntentDecomposition, 실패 시 None
        """
        try:
            structured_model = self._get_structured_model()
        except ImportError:
            logger.warning("langchain-ollama 패키지가 없어 규칙 기반 구조분해를 사용합니다.")
            return None

        if is_prompt_trace_enabled():
            logger.info("prompt_trace.intent_request: %s", prompt)

        try:
            from ollama import ResponseError as OllamaResponseError
        except ImportError:
            OllamaResponseError = RuntimeError

        try:
            result = structured_model.invoke(prompt)
        except (ConnectionError, TimeoutError, RuntimeError, ValueError, TypeError, OllamaResponseError) as exc:
            logger.warning("Ollama 구조분해 호출 실패: %s", exc)
            return None
        if is_prompt_trace_enabled():
            logger.info("prompt_trace.intent_response: %s", _serialize_intent_result(result=result))

        if isinstance(result, IntentDecomposition):
            return result
        if isinstance(result, str):
            parsed = _parse_intent_json_from_text(text=result)
            if parsed is None:
                logger.warning("Ollama 구조분해 문자열 결과 파싱 실패")
                return None
            return parsed
        try:
            return IntentDecomposition.model_validate(result)
        except ValidationError as exc:
            logger.warning("Ollama 구조분해 결과 검증 실패: %s", exc)
            return None


def _serialize_intent_result(result: object) -> str:
    """
    intent parser 모델 응답 객체를 로그 문자열로 변환한다.

    Args:
        result: structured invoke 결과 객체

    Returns:
        로그 출력용 문자열
    """
    if isinstance(result, IntentDecomposition):
        return result.model_dump_json(ensure_ascii=False)
    return str(result)


def _normalize_fast_path_mode(raw_mode: str) -> str:
    """
    intent fast-path 모드 문자열을 허용값으로 정규화한다.

    Args:
        raw_mode: 환경변수/입력 모드 문자열

    Returns:
        `auto`, `always`, `never` 중 하나
    """
    mode = str(raw_mode or "").strip().lower()
    if mode in {"auto", "always", "never"}:
        return mode
    return DEFAULT_INTENT_FAST_PATH_MODE


def _normalize_max_steps(raw_max_steps: int | str) -> int:
    """
    step 상한 입력값을 안전한 정수로 정규화한다.

    Args:
        raw_max_steps: 환경변수/입력 상한값

    Returns:
        1 이상 정규화된 step 상한
    """
    try:
        value = int(raw_max_steps)
    except (TypeError, ValueError):
        return DEFAULT_INTENT_MAX_STEPS
    return value if value > 0 else DEFAULT_INTENT_MAX_STEPS


def _limit_execution_steps(steps: list[ExecutionStep], max_steps: int) -> list[ExecutionStep]:
    """
    step 목록을 우선순위 기준으로 정렬한 뒤 상한 개수로 제한한다.

    Args:
        steps: 원본 step 목록
        max_steps: 허용 최대 step 개수

    Returns:
        우선순위/상한이 반영된 step 목록
    """
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
    limited = [step for _, step in ranked[:max_steps]]
    return limited


def _apply_step_limit_to_decomposition(
    decomposition: IntentDecomposition,
    max_steps: int,
) -> IntentDecomposition:
    """
    구조분해 결과에 step 상한을 적용해 최종 객체를 재구성한다.

    Args:
        decomposition: 원본 구조분해 결과
        max_steps: step 상한

    Returns:
        step 상한이 반영된 구조분해 결과
    """
    required_steps = _infer_required_steps_from_query(user_message=decomposition.original_query)
    effective_max_steps = max(max_steps, len(required_steps))
    limited_steps = _limit_execution_steps_with_required(
        steps=decomposition.steps,
        max_steps=effective_max_steps,
        required_steps=required_steps,
    )
    return IntentDecomposition(
        original_query=decomposition.original_query,
        steps=limited_steps,
        summary_line_target=decomposition.summary_line_target,
        date_filter=decomposition.date_filter,
        missing_slots=_build_missing_slots(
            steps=limited_steps,
            user_message=decomposition.original_query,
        ),
    )


def _try_simple_fast_path(user_message: str, fast_path_mode: str) -> IntentDecomposition | None:
    """
    fast-path 모드에 따라 규칙 기반 사전 분해를 시도한다.

    Args:
        user_message: 사용자 입력
        fast_path_mode: fast-path 모드

    Returns:
        적용 결과가 있으면 IntentDecomposition, 없으면 None
    """
    if fast_path_mode == "never":
        return None
    if fast_path_mode == "always":
        return _rule_based_decomposition(user_message=user_message)
    simple = _build_simple_fast_path_decomposition(user_message=user_message)
    if simple is not None:
        return simple
    if _is_rule_fast_path_candidate(user_message=user_message):
        return _rule_based_decomposition(user_message=user_message)
    return None


def _is_rule_fast_path_candidate(user_message: str) -> bool:
    """
    auto 모드에서 Ollama 호출을 생략해도 되는 규칙 기반 fast-path 후보인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        규칙 기반 단계 추출이 가능하면 True
    """
    inferred_steps = infer_steps_from_query(user_message=user_message)
    return bool(inferred_steps)


def _build_simple_fast_path_decomposition(user_message: str) -> IntentDecomposition | None:
    """
    초단순 패턴 질의에 대해서만 fast-path 구조분해를 생성한다.

    Args:
        user_message: 사용자 입력

    Returns:
        패턴 적중 시 IntentDecomposition, 아니면 None
    """
    compact = re.sub(r"\s+", "", user_message)
    for pattern, steps in SIMPLE_FAST_PATH_PATTERNS:
        if not pattern.fullmatch(compact):
            continue
        return IntentDecomposition(
            original_query=user_message,
            steps=steps,
            summary_line_target=extract_summary_line_target(user_message=user_message),
            date_filter=_build_date_filter(user_message=user_message),
            missing_slots=_build_missing_slots(steps=steps, user_message=user_message),
        )
    return None


def _is_valid_decomposition(decomposition: IntentDecomposition, user_message: str) -> bool:
    """
    모델 구조분해 결과가 최소 품질 기준을 만족하는지 검증한다.

    Args:
        decomposition: 구조분해 결과
        user_message: 사용자 입력

    Returns:
        품질 기준을 만족하면 True
    """
    if not decomposition.steps:
        return False
    required_steps = _infer_required_steps_from_query(user_message=user_message)
    return required_steps.issubset(set(decomposition.steps))


def _infer_required_steps_from_query(user_message: str) -> set[ExecutionStep]:
    """
    사용자 질의의 핵심 키워드에서 필수 step 집합을 계산한다.

    Args:
        user_message: 사용자 입력

    Returns:
        필수 실행 단계 집합
    """
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
    if "요약" in text or "정리" in text or "보고서" in text:
        required.add(ExecutionStep.SUMMARIZE_MAIL)
    if "예약" in text or "잡아" in text:
        required.add(ExecutionStep.BOOK_MEETING_ROOM)
    if "일정" in text and ("등록" in text or "추가" in text or "생성" in text) and "회의실" not in text:
        required.add(ExecutionStep.BOOK_CALENDAR_EVENT)
    return required


def _limit_execution_steps_with_required(
    steps: list[ExecutionStep],
    max_steps: int,
    required_steps: set[ExecutionStep],
) -> list[ExecutionStep]:
    """
    step 상한 적용 시 required step이 누락되지 않도록 보정한다.

    Args:
        steps: 원본 step 목록
        max_steps: 허용 최대 step 수
        required_steps: 질의로부터 계산된 필수 step 집합

    Returns:
        required step 보존이 반영된 step 목록
    """
    if not steps:
        return []
    normalized_required = [step for step in steps if step in required_steps]
    if len(steps) <= max_steps:
        return steps

    limited = _limit_execution_steps(steps=steps, max_steps=max_steps)
    for required in normalized_required:
        if required in limited:
            continue
        replace_index = _find_replaceable_index(limited=limited, required_steps=required_steps)
        if replace_index is None:
            limited.append(required)
            continue
        limited[replace_index] = required
    return _dedupe_steps_preserve_order(steps=limited)


def _find_replaceable_index(
    limited: list[ExecutionStep],
    required_steps: set[ExecutionStep],
) -> int | None:
    """
    제한된 step 목록에서 required를 대체 삽입할 인덱스를 찾는다.

    Args:
        limited: 상한 적용된 step 목록
        required_steps: 필수 step 집합

    Returns:
        대체 가능한 인덱스, 없으면 None
    """
    candidates = [
        (index, STEP_PRIORITY.get(step, 999))
        for index, step in enumerate(limited)
        if step not in required_steps
    ]
    if not candidates:
        return None
    # 우선순위가 가장 낮은 step(숫자가 큰 step)을 대체한다.
    candidates.sort(key=lambda item: item[1], reverse=True)
    return candidates[0][0]


def _dedupe_steps_preserve_order(steps: list[ExecutionStep]) -> list[ExecutionStep]:
    """
    step 목록에서 순서를 유지한 채 중복을 제거한다.

    Args:
        steps: 원본 step 목록

    Returns:
        중복 제거 step 목록
    """
    deduped: list[ExecutionStep] = []
    for step in steps:
        if step in deduped:
            continue
        deduped.append(step)
    return deduped


def _parse_intent_json_from_text(text: str) -> IntentDecomposition | None:
    """
    코드블록/평문으로 감싸진 JSON 문자열을 IntentDecomposition으로 파싱한다.

    Args:
        text: 모델 원문 응답

    Returns:
        파싱 성공 시 IntentDecomposition, 실패 시 None
    """
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


@lru_cache(maxsize=1)
def get_intent_parser() -> ExaoneIntentParser:
    """
    애플리케이션 전역에서 재사용할 Exaone 파서를 반환한다.

    Returns:
        캐시된 ExaoneIntentParser 인스턴스
    """
    model_name = str(os.getenv("MOLDUBOT_INTENT_MODEL", DEFAULT_EXAONE_MODEL)).strip() or DEFAULT_EXAONE_MODEL
    base_url = str(os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)).strip() or DEFAULT_OLLAMA_BASE_URL
    fast_path_mode = str(os.getenv("MOLDUBOT_INTENT_FAST_PATH", DEFAULT_INTENT_FAST_PATH_MODE)).strip()
    max_steps = _normalize_max_steps(
        raw_max_steps=os.getenv("MOLDUBOT_INTENT_MAX_STEPS", str(DEFAULT_INTENT_MAX_STEPS))
    )
    logger.info(
        "ExaoneIntentParser 초기화: model=%s base_url=%s fast_path_mode=%s max_steps=%s",
        model_name,
        base_url,
        _normalize_fast_path_mode(raw_mode=fast_path_mode),
        max_steps,
    )
    return ExaoneIntentParser(
        model_name=model_name,
        base_url=base_url,
        temperature=0.0,
        fast_path_mode=fast_path_mode,
        max_steps=max_steps,
    )
