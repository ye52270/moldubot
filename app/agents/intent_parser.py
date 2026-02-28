from __future__ import annotations

import os
from functools import lru_cache

from pydantic import ValidationError

from app.core.logging_config import get_logger
from app.core.intent_rules import (
    build_missing_slots,
    extract_date_filter_fields,
    extract_summary_line_target,
    infer_steps_from_query,
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
    inferred_steps = infer_steps_from_query(user_message=user_message)
    step_map = {
        "read_current_mail": ExecutionStep.READ_CURRENT_MAIL,
        "summarize_mail": ExecutionStep.SUMMARIZE_MAIL,
        "extract_key_facts": ExecutionStep.EXTRACT_KEY_FACTS,
        "extract_recipients": ExecutionStep.EXTRACT_RECIPIENTS,
        "search_meeting_schedule": ExecutionStep.SEARCH_MEETING_SCHEDULE,
        "book_meeting_room": ExecutionStep.BOOK_MEETING_ROOM,
    }
    for step in inferred_steps:
        mapped_step = step_map.get(step)
        if mapped_step is not None:
            normalized.append(mapped_step)

    # 규칙 추출 결과가 비어 있으면 모델 결과를 보조로 사용하되 중복은 제거한다.
    if not normalized:
        for step in raw_steps:
            if step not in normalized:
                normalized.append(step)

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

    def __init__(self, model_name: str, base_url: str, temperature: float = 0.0) -> None:
        """
        Exaone 파서 인스턴스를 초기화한다.

        Args:
            model_name: Ollama 모델 이름
            base_url: Ollama 서버 URL
            temperature: 생성 온도
        """
        self._model_name = model_name
        self._base_url = base_url
        self._temperature = temperature

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

        prompt = self._build_prompt(user_message=sanitized_query)
        parsed = self._invoke_ollama_structured(prompt=prompt)
        if parsed is None:
            logger.info("Ollama 구조분해 실패로 규칙 기반 분해로 전환합니다.")
            return _rule_based_decomposition(user_message=sanitized_query)

        normalized_steps = _normalize_steps(raw_steps=parsed.steps, user_message=sanitized_query)
        decomposition = IntentDecomposition(
            original_query=sanitized_query,
            steps=normalized_steps,
            summary_line_target=extract_summary_line_target(user_message=sanitized_query),
            date_filter=_build_date_filter(user_message=sanitized_query),
            missing_slots=_build_missing_slots(steps=normalized_steps, user_message=sanitized_query),
        )
        logger.info("Ollama 구조분해 성공: steps=%s", [step.value for step in decomposition.steps])
        return decomposition

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
            "7) 회의예약이 있으면 missing_slots에 date,start_time,end_time,attendee_count 누락값을 채운다.\n\n"
            "허용 steps: read_current_mail, summarize_mail, extract_key_facts, extract_recipients, "
            "search_meeting_schedule, book_meeting_room\n\n"
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
            from langchain_ollama import ChatOllama
        except ImportError:
            logger.warning("langchain-ollama 패키지가 없어 규칙 기반 구조분해를 사용합니다.")
            return None

        model = ChatOllama(
            model=self._model_name,
            base_url=self._base_url,
            temperature=self._temperature,
        )
        structured_model = model.with_structured_output(IntentDecomposition)

        try:
            from ollama import ResponseError as OllamaResponseError
        except ImportError:
            OllamaResponseError = RuntimeError

        try:
            result = structured_model.invoke(prompt)
        except (ConnectionError, TimeoutError, RuntimeError, ValueError, TypeError, OllamaResponseError) as exc:
            logger.warning("Ollama 구조분해 호출 실패: %s", exc)
            return None

        if isinstance(result, IntentDecomposition):
            return result
        try:
            return IntentDecomposition.model_validate(result)
        except ValidationError as exc:
            logger.warning("Ollama 구조분해 결과 검증 실패: %s", exc)
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
    logger.info("ExaoneIntentParser 초기화: model=%s base_url=%s", model_name, base_url)
    return ExaoneIntentParser(model_name=model_name, base_url=base_url, temperature=0.0)
