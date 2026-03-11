from __future__ import annotations

import os
from collections import OrderedDict
from functools import lru_cache
from typing import Any

from langchain.chat_models import init_chat_model
from pydantic import ValidationError

from app.agents.intent_parser_utils import (
    DEFAULT_INTENT_FAST_PATH_MODE,
    DEFAULT_INTENT_MAX_STEPS,
    apply_step_limit_to_decomposition,
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
from app.core.intent_rules import sanitize_user_query
from app.core.llm_runtime import normalize_model_name, resolve_env_model
from app.core.logging_config import get_logger, is_prompt_trace_enabled

DEFAULT_INTENT_BASE_URL = ""
DEFAULT_INTENT_MODEL = "azure_openai:gpt-4o-mini"
INTENT_PARSE_CACHE_SIZE = 128
DEFAULT_INTENT_TIMEOUT_SEC = 60

logger = get_logger(__name__)


class IntentParser:
    """구조화 출력 LLM으로 최소 의도 구조분해를 수행하는 파서 클래스."""

    def __init__(
        self,
        model_name: str,
        base_url: str,
        temperature: float = 0.0,
        fast_path_mode: str = DEFAULT_INTENT_FAST_PATH_MODE,
        max_steps: int = DEFAULT_INTENT_MAX_STEPS,
        timeout_sec: int = DEFAULT_INTENT_TIMEOUT_SEC,
    ) -> None:
        """의도 파서 인스턴스를 초기화한다."""
        self._model_name = model_name
        self._base_url = base_url
        self._temperature = temperature
        self._fast_path_mode = normalize_fast_path_mode(raw_mode=fast_path_mode)
        self._max_steps = normalize_max_steps(raw_max_steps=max_steps)
        self._timeout_sec = max(1, int(timeout_sec))
        self._structured_model: Any = None
        self._parse_cache: OrderedDict[str, IntentDecomposition] = OrderedDict()

    def parse(
        self,
        user_message: str,
        has_selected_mail: bool = False,
        selected_message_id_exists: bool = False,
    ) -> IntentDecomposition:
        """사용자 문장을 최소 의도 구조분해 형태로 변환한다."""
        sanitized_query = sanitize_user_query(user_message=user_message)
        if not sanitized_query:
            logger.info("의도 구조분해 입력이 비어 기본 분해를 반환합니다.")
            return create_default_decomposition(user_message=user_message)
        cache_key = self._build_cache_key(
            sanitized_query=sanitized_query,
            has_selected_mail=has_selected_mail,
            selected_message_id_exists=selected_message_id_exists,
        )

        cached = self._read_cached_decomposition(cache_key=cache_key)
        if cached is not None:
            logger.info("intent parse cache hit")
            cached = cached.model_copy(update={"origin": "llm_cached"})
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
            fast_path_result = fast_path_result.model_copy(update={"origin": "llm_fresh"})
            final_decomposition = apply_step_limit_to_decomposition(
                decomposition=fast_path_result,
                max_steps=self._max_steps,
            )
            self._write_cached_decomposition(cache_key=cache_key, decomposition=final_decomposition)
            return final_decomposition

        prompt = self._build_prompt(user_message=sanitized_query)
        parsed = self._invoke_structured_llm(prompt=prompt)
        if parsed is None:
            logger.info("LLM 구조분해 실패로 규칙 기반 분해로 전환합니다.")
            fallback = apply_step_limit_to_decomposition(
                decomposition=rule_based_decomposition(user_message=sanitized_query),
                max_steps=self._max_steps,
            )
            fallback = fallback.model_copy(update={"origin": "llm_fresh"})
            self._write_cached_decomposition(cache_key=cache_key, decomposition=fallback)
            return fallback

        normalized_steps = normalize_steps(
            raw_steps=parsed.steps,
            user_message=sanitized_query,
            allow_rule_fallback=False,
        )
        parsed_payload = parsed.model_dump()
        parsed_payload["original_query"] = sanitized_query
        parsed_payload["steps"] = normalized_steps
        parsed_payload["origin"] = "llm_fresh"
        decomposition = IntentDecomposition.model_validate(parsed_payload)
        decomposition = decomposition.model_copy(update={"origin": "llm_fresh"})
        decomposition = apply_step_limit_to_decomposition(
            decomposition=decomposition,
            max_steps=self._max_steps,
            enforce_required_steps=False,
        )
        if not is_valid_decomposition(
            decomposition=decomposition,
            user_message=sanitized_query,
            enforce_required_steps=False,
        ):
            logger.warning("LLM 구조분해 품질 검증 실패로 규칙 기반 분해로 전환합니다.")
            fallback = apply_step_limit_to_decomposition(
                decomposition=rule_based_decomposition(user_message=sanitized_query),
                max_steps=self._max_steps,
            )
            fallback = fallback.model_copy(update={"origin": "llm_fresh"})
            self._write_cached_decomposition(cache_key=cache_key, decomposition=fallback)
            return fallback

        logger.info("LLM 구조분해 성공: steps=%s", [step.value for step in decomposition.steps])
        self._write_cached_decomposition(cache_key=cache_key, decomposition=decomposition)
        return decomposition

    def _build_cache_key(
        self,
        sanitized_query: str,
        has_selected_mail: bool,
        selected_message_id_exists: bool,
    ) -> str:
        """질의/선택메일 namespace를 결합한 intent cache key를 생성한다."""
        namespace = (
            f"has_selected_mail={int(bool(has_selected_mail))}|"
            f"selected_message_id_exists={int(bool(selected_message_id_exists))}"
        )
        return f"{sanitized_query}|{namespace}"

    def _read_cached_decomposition(self, cache_key: str) -> IntentDecomposition | None:
        """동일 질의에 대한 구조분해 캐시를 조회한다."""
        cached = self._parse_cache.get(cache_key)
        if cached is None:
            return None
        self._parse_cache.move_to_end(cache_key)
        return cached.model_copy(deep=True)

    def _write_cached_decomposition(self, cache_key: str, decomposition: IntentDecomposition) -> None:
        """구조분해 결과를 LRU 캐시에 저장한다."""
        self._parse_cache[cache_key] = decomposition.model_copy(deep=True)
        self._parse_cache.move_to_end(cache_key)
        while len(self._parse_cache) > INTENT_PARSE_CACHE_SIZE:
            self._parse_cache.popitem(last=False)

    def _get_structured_model(self) -> Any:
        """의도 구조분해 structured output 모델 인스턴스를 재사용한다."""
        if self._structured_model is not None:
            return self._structured_model
        normalized_model = normalize_model_name(
            model_name=self._model_name,
            default_model=DEFAULT_INTENT_MODEL,
        )
        model_kwargs: dict[str, Any] = {
            "model": normalized_model,
            "temperature": self._temperature,
            "timeout": self._timeout_sec,
        }
        if normalized_model.startswith("ollama:") and str(self._base_url or "").strip():
            model_kwargs["base_url"] = self._base_url.strip()
        model = init_chat_model(**model_kwargs)
        self._structured_model = model.with_structured_output(IntentDecomposition)
        return self._structured_model

    def _build_prompt(self, user_message: str) -> str:
        """의도 최소 구조분해 프롬프트를 생성한다."""
        return (
            '너는 "의도 JSON 슬롯 파서"다. 생성형 비서가 아니라 분류기처럼 동작한다.\n\n'
            "절대 규칙:\n"
            "1) JSON 객체 1개만 출력한다. 설명/주석/코드블록/마크다운 금지.\n"
            "2) 아래 스키마의 키를 모두 포함한다. 키 이름 변경/추가/삭제 금지.\n"
            "3) enum 허용값 외 값 금지.\n"
            "4) 입력에 없는 정보는 추측하지 않는다.\n"
            "5) self-check 결과를 텍스트로 출력하지 않는다.\n"
            "6) 최종 출력은 raw JSON 1개만 출력한다.\n\n"
            "의도 우선순위(충돌 시 상위만 채택):\n"
            "translation > action > retrieval > summary > analysis > extraction > general\n\n"
            "steps 허용값(이 외 사용 금지):\n"
            "read_current_mail, summarize_mail, extract_key_facts, extract_recipients, "
            "search_mails, search_meeting_schedule, book_meeting_room, book_calendar_event\n\n"
            "task_type 허용값:\n"
            "general, summary, extraction, analysis, solution, retrieval, action\n\n"
            "output_format 허용값:\n"
            "general, structured_template, detailed_summary, line_summary, "
            "table, issue_action, schedule_owner_action, translation\n\n"
            "focus_topics 허용값:\n"
            "mail_general, recipients, cost, tech_issue, schedule, ssl\n\n"
            "date_filter.mode 허용값:\n"
            "none, relative, absolute\n\n"
            "강제 규칙:\n"
            '- "번역", "translate", "translation"이 입력에 포함되면:\n'
            '  - output_format = "translation"\n'
            '  - task_type = "general"\n'
            '  - 현재메일 문맥(예: "현재메일", "현재 선택 메일", "[질의 범위] 현재 선택 메일 1건만 기준으로 처리")이면 steps = ["read_current_mail"] 만 사용\n'
            '  - output_format = "structured_template" 금지\n'
            '- "[질의 범위] 현재 선택 메일 1건만 기준으로 처리"가 있으면:\n'
            "  - search_mails는 기본 금지\n"
            '  - 단, "다른 메일", "관련 메일 찾아", "유사 메일 검색"처럼 명시적 탐색 의도일 때만 허용\n'
            '  - steps에 "read_current_mail" 포함\n'
            '- "N줄", "N개", "N가지" 요약 요청이면 summary_line_target = N\n'
            "- 날짜/수신시점 표현이 없으면 date_filter.mode = none\n"
            '  - "N월분", "N분기분", "상반기분", "하반기분" 같은 표현은 청구/정산 기간을 의미하므로 date_filter는 반드시 none으로 한다.\n'
            '  - 날짜 필터는 "이번 주", "어제", "지난달에 받은", "1월에 온"처럼 명시적으로 수신 시점을 가리키는 표현에만 적용한다.\n\n'
            "금지 조합:\n"
            '- output_format="translation" AND task_type in ["summary","extraction","analysis","solution","retrieval","action"]\n'
            '- 현재메일 번역 요청에서 output_format="structured_template"\n'
            "- 번역 요청에서 steps에 extract_key_facts 포함 금지\n\n"
            "출력 스키마(모든 키 필수):\n"
            "{\n"
            '  "original_query": "",\n'
            '  "steps": [],\n'
            '  "summary_line_target": 5,\n'
            '  "date_filter": {"mode":"none|relative|absolute","relative":"","start":"","end":""},\n'
            '  "missing_slots": [],\n'
            '  "task_type": "general|summary|extraction|analysis|solution|retrieval|action",\n'
            '  "output_format": "general|structured_template|detailed_summary|line_summary|table|issue_action|schedule_owner_action|translation",\n'
            '  "focus_topics": ["mail_general|recipients|cost|tech_issue|schedule|ssl"],\n'
            '  "confidence": 0.5\n'
            "}\n\n"
            "Few-shot:\n"
            "입력: [질의 범위] 현재 선택 메일 1건만 기준으로 처리\n"
            "내 구독이 어떻게 되는지 알려줘\n"
            "출력: {\"original_query\":\"내 구독이 어떻게 되는지 알려줘\",\"steps\":[\"read_current_mail\",\"extract_key_facts\"],\"summary_line_target\":5,\"date_filter\":{\"mode\":\"none\",\"relative\":\"\",\"start\":\"\",\"end\":\"\"},\"missing_slots\":[],\"task_type\":\"extraction\",\"output_format\":\"general\",\"focus_topics\":[\"mail_general\"],\"confidence\":0.9}\n\n"
            "입력: 현재메일과 관련된 다른 메일 찾아줘\n"
            "출력: {\"original_query\":\"현재메일과 관련된 다른 메일 찾아줘\",\"steps\":[\"read_current_mail\",\"search_mails\"],\"summary_line_target\":5,\"date_filter\":{\"mode\":\"none\",\"relative\":\"\",\"start\":\"\",\"end\":\"\"},\"missing_slots\":[],\"task_type\":\"retrieval\",\"output_format\":\"general\",\"focus_topics\":[\"mail_general\"],\"confidence\":0.9}\n\n"
            "입력: 현재메일 번역해줘\n"
            "출력: {\"original_query\":\"현재메일 번역해줘\",\"steps\":[\"read_current_mail\"],\"summary_line_target\":5,\"date_filter\":{\"mode\":\"none\",\"relative\":\"\",\"start\":\"\",\"end\":\"\"},\"missing_slots\":[],\"task_type\":\"general\",\"output_format\":\"translation\",\"focus_topics\":[\"mail_general\"],\"confidence\":0.95}\n\n"
            "FINAL CHECK(내부 검사만 수행, 결과 텍스트 출력 금지):\n"
            "- 의도 우선순위 위반 여부\n"
            "- enum 허용값 외 사용 여부\n"
            "- 금지 조합 위반 여부\n"
            "- 번역 요청인데 output_format이 translation이 아닌지 여부\n"
            "- 번역 요청인데 steps에 extract_key_facts가 포함됐는지 여부\n"
            "위반 시 JSON을 수정한 뒤 최종 JSON 1개만 출력한다.\n\n"
            f"사용자 입력: {user_message}\n"
            "출력: JSON 객체 1개"
        )

    def _invoke_structured_llm(self, prompt: str) -> IntentDecomposition | None:
        """구조화 출력 LLM 호출로 구조분해 결과를 얻는다."""
        structured_model = self._get_structured_model()

        if is_prompt_trace_enabled():
            logger.info("prompt_trace.intent_request: %s", prompt)

        try:
            result = structured_model.invoke(prompt)
        except (ConnectionError, TimeoutError, RuntimeError, ValueError, TypeError) as exc:
            logger.warning("LLM 구조분해 호출 실패: %s", exc)
            return None
        if is_prompt_trace_enabled():
            logger.info("prompt_trace.intent_response: %s", serialize_intent_result(result=result))

        if isinstance(result, IntentDecomposition):
            return result
        if isinstance(result, str):
            parsed = parse_intent_json_from_text(text=result)
            if parsed is None:
                logger.warning("LLM 구조분해 문자열 결과 파싱 실패")
                return None
            return parsed
        try:
            return IntentDecomposition.model_validate(result)
        except ValidationError as exc:
            logger.warning("LLM 구조분해 결과 검증 실패: %s", exc)
            return None


@lru_cache(maxsize=1)
def get_intent_parser() -> IntentParser:
    """애플리케이션 전역에서 재사용할 의도 파서를 반환한다."""
    model_name = resolve_env_model(
        primary_env="MOLDUBOT_INTENT_MODEL",
        fallback_envs=("MOLDUBOT_AGENT_MODEL", "DEFAULT_CHAT_MODEL"),
        default_model=DEFAULT_INTENT_MODEL,
    )
    base_url = str(os.getenv("MOLDUBOT_INTENT_BASE_URL", DEFAULT_INTENT_BASE_URL)).strip()
    fast_path_mode = str(os.getenv("MOLDUBOT_INTENT_FAST_PATH", DEFAULT_INTENT_FAST_PATH_MODE)).strip()
    max_steps = normalize_max_steps(
        raw_max_steps=os.getenv("MOLDUBOT_INTENT_MAX_STEPS", str(DEFAULT_INTENT_MAX_STEPS))
    )
    timeout_raw = str(os.getenv("MOLDUBOT_INTENT_TIMEOUT_SEC", str(DEFAULT_INTENT_TIMEOUT_SEC))).strip()
    try:
        timeout_sec = int(timeout_raw or str(DEFAULT_INTENT_TIMEOUT_SEC))
    except ValueError:
        timeout_sec = DEFAULT_INTENT_TIMEOUT_SEC
        logger.warning(
            "MOLDUBOT_INTENT_TIMEOUT_SEC 값이 유효하지 않아 기본값을 사용합니다: raw=%s default=%s",
            timeout_raw,
            DEFAULT_INTENT_TIMEOUT_SEC,
        )
    logger.info(
        "IntentParser 초기화: model=%s base_url=%s fast_path_mode=%s max_steps=%s timeout_sec=%s",
        model_name,
        base_url,
        normalize_fast_path_mode(raw_mode=fast_path_mode),
        max_steps,
        timeout_sec,
    )
    return IntentParser(
        model_name=model_name,
        base_url=base_url,
        temperature=0.0,
        fast_path_mode=fast_path_mode,
        max_steps=max_steps,
        timeout_sec=timeout_sec,
    )
