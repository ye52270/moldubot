from __future__ import annotations

import os
from collections import OrderedDict
from functools import lru_cache
from typing import Any

from pydantic import ValidationError

from app.agents.intent_parser_utils import (
    DEFAULT_INTENT_FAST_PATH_MODE,
    DEFAULT_INTENT_MAX_STEPS,
    apply_step_limit_to_decomposition,
    build_date_filter,
    compose_decomposition,
    is_valid_decomposition,
    normalize_fast_path_mode,
    normalize_max_steps,
    normalize_steps,
    parse_intent_json_from_text,
    rule_based_decomposition,
    serialize_intent_result,
    try_simple_fast_path,
)
from app.agents.intent_schema import IntentDecomposition, create_default_decomposition
from app.core.intent_rules import extract_summary_line_target, sanitize_user_query
from app.core.logging_config import get_logger, is_prompt_trace_enabled

DEFAULT_OLLAMA_BASE_URL = "http://127.0.0.1:11434"
DEFAULT_EXAONE_MODEL = "exaone3.5:2.4b"
INTENT_PARSE_CACHE_SIZE = 128

logger = get_logger(__name__)


class ExaoneIntentParser:
    """Ollama Exaone 모델로 최소 구조분해를 수행하는 파서 클래스."""

    def __init__(
        self,
        model_name: str,
        base_url: str,
        temperature: float = 0.0,
        fast_path_mode: str = DEFAULT_INTENT_FAST_PATH_MODE,
        max_steps: int = DEFAULT_INTENT_MAX_STEPS,
    ) -> None:
        """Exaone 파서 인스턴스를 초기화한다."""
        self._model_name = model_name
        self._base_url = base_url
        self._temperature = temperature
        self._fast_path_mode = normalize_fast_path_mode(raw_mode=fast_path_mode)
        self._max_steps = normalize_max_steps(raw_max_steps=max_steps)
        self._structured_model: Any = None
        self._parse_cache: OrderedDict[str, IntentDecomposition] = OrderedDict()

    def parse(self, user_message: str) -> IntentDecomposition:
        """사용자 문장을 최소 의도 구조분해 형태로 변환한다."""
        sanitized_query = sanitize_user_query(user_message=user_message)
        if not sanitized_query:
            logger.info("의도 구조분해 입력이 비어 기본 분해를 반환합니다.")
            return create_default_decomposition(user_message=user_message)

        cached = self._read_cached_decomposition(user_message=sanitized_query)
        if cached is not None:
            logger.info("intent parse cache hit")
            return apply_step_limit_to_decomposition(
                decomposition=cached,
                max_steps=self._max_steps,
            )

        fast_path_result = try_simple_fast_path(
            user_message=sanitized_query,
            fast_path_mode=self._fast_path_mode,
        )
        if fast_path_result is not None:
            logger.info("intent fast-path 적용: mode=%s", self._fast_path_mode)
            final_decomposition = apply_step_limit_to_decomposition(
                decomposition=fast_path_result,
                max_steps=self._max_steps,
            )
            self._write_cached_decomposition(user_message=sanitized_query, decomposition=final_decomposition)
            return final_decomposition

        prompt = self._build_prompt(user_message=sanitized_query)
        parsed = self._invoke_ollama_structured(prompt=prompt)
        if parsed is None:
            logger.info("Ollama 구조분해 실패로 규칙 기반 분해로 전환합니다.")
            fallback = apply_step_limit_to_decomposition(
                decomposition=rule_based_decomposition(user_message=sanitized_query),
                max_steps=self._max_steps,
            )
            self._write_cached_decomposition(user_message=sanitized_query, decomposition=fallback)
            return fallback

        normalized_steps = normalize_steps(raw_steps=parsed.steps, user_message=sanitized_query)
        decomposition = compose_decomposition(
            user_message=sanitized_query,
            steps=normalized_steps,
            summary_line_target=extract_summary_line_target(user_message=sanitized_query),
            date_filter=build_date_filter(user_message=sanitized_query),
        )
        decomposition = apply_step_limit_to_decomposition(
            decomposition=decomposition,
            max_steps=self._max_steps,
        )
        if not is_valid_decomposition(decomposition=decomposition, user_message=sanitized_query):
            logger.warning("Ollama 구조분해 품질 검증 실패로 규칙 기반 분해로 전환합니다.")
            fallback = apply_step_limit_to_decomposition(
                decomposition=rule_based_decomposition(user_message=sanitized_query),
                max_steps=self._max_steps,
            )
            self._write_cached_decomposition(user_message=sanitized_query, decomposition=fallback)
            return fallback

        logger.info("Ollama 구조분해 성공: steps=%s", [step.value for step in decomposition.steps])
        self._write_cached_decomposition(user_message=sanitized_query, decomposition=decomposition)
        return decomposition

    def _read_cached_decomposition(self, user_message: str) -> IntentDecomposition | None:
        """동일 질의에 대한 구조분해 캐시를 조회한다."""
        cached = self._parse_cache.get(user_message)
        if cached is None:
            return None
        self._parse_cache.move_to_end(user_message)
        return cached.model_copy(deep=True)

    def _write_cached_decomposition(self, user_message: str, decomposition: IntentDecomposition) -> None:
        """구조분해 결과를 LRU 캐시에 저장한다."""
        self._parse_cache[user_message] = decomposition.model_copy(deep=True)
        self._parse_cache.move_to_end(user_message)
        while len(self._parse_cache) > INTENT_PARSE_CACHE_SIZE:
            self._parse_cache.popitem(last=False)

    def _get_structured_model(self) -> Any:
        """Ollama structured output 모델 인스턴스를 재사용한다."""
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
        """Exaone 최소 구조분해 프롬프트를 생성한다."""
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
            '  "missing_slots": [],\n'
            '  "task_type": "general|summary|extraction|analysis|solution|retrieval|action",\n'
            '  "output_format": "general|structured_template|detailed_summary|line_summary|table|issue_action|schedule_owner_action",\n'
            '  "focus_topics": ["mail_general|recipients|cost|tech_issue|schedule|ssl"],\n'
            '  "confidence": 0.5\n'
            "}\n\n"
            f"사용자 입력: {user_message}\n"
            "출력: JSON 객체 1개"
        )

    def _invoke_ollama_structured(self, prompt: str) -> IntentDecomposition | None:
        """Ollama structured output 호출로 구조분해 결과를 얻는다."""
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
            logger.info("prompt_trace.intent_response: %s", serialize_intent_result(result=result))

        if isinstance(result, IntentDecomposition):
            return result
        if isinstance(result, str):
            parsed = parse_intent_json_from_text(text=result)
            if parsed is None:
                logger.warning("Ollama 구조분해 문자열 결과 파싱 실패")
                return None
            return parsed
        try:
            return IntentDecomposition.model_validate(result)
        except ValidationError as exc:
            logger.warning("Ollama 구조분해 결과 검증 실패: %s", exc)
            return None


@lru_cache(maxsize=1)
def get_intent_parser() -> ExaoneIntentParser:
    """애플리케이션 전역에서 재사용할 Exaone 파서를 반환한다."""
    model_name = str(os.getenv("MOLDUBOT_INTENT_MODEL", DEFAULT_EXAONE_MODEL)).strip() or DEFAULT_EXAONE_MODEL
    base_url = str(os.getenv("OLLAMA_BASE_URL", DEFAULT_OLLAMA_BASE_URL)).strip() or DEFAULT_OLLAMA_BASE_URL
    fast_path_mode = str(os.getenv("MOLDUBOT_INTENT_FAST_PATH", DEFAULT_INTENT_FAST_PATH_MODE)).strip()
    max_steps = normalize_max_steps(
        raw_max_steps=os.getenv("MOLDUBOT_INTENT_MAX_STEPS", str(DEFAULT_INTENT_MAX_STEPS))
    )
    logger.info(
        "ExaoneIntentParser 초기화: model=%s base_url=%s fast_path_mode=%s max_steps=%s",
        model_name,
        base_url,
        normalize_fast_path_mode(raw_mode=fast_path_mode),
        max_steps,
    )
    return ExaoneIntentParser(
        model_name=model_name,
        base_url=base_url,
        temperature=0.0,
        fast_path_mode=fast_path_mode,
        max_steps=max_steps,
    )
