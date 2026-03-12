from __future__ import annotations

import os
from contextvars import ContextVar
from functools import lru_cache
from typing import Any, Mapping

from deepagents import create_deep_agent
from langgraph.checkpoint.memory import InMemorySaver
from langgraph.types import Command

from app.agents.agent_runtime_config import resolve_agent_skills_paths
from app.agents.deep_chat_agent_utils import (
    extract_assistant_text,
    extract_interrupt_requests,
    extract_interrupt_requests_from_state,
    extract_latest_tool_payload,
    resolve_thread_id,
)
from app.agents.prompts import get_agent_system_prompt, get_default_agent_system_prompt
from app.agents.subagents import get_agent_subagents
from app.agents.tools import get_agent_tools
from app.core.llm_runtime import is_model_provider_configured, resolve_env_model
from app.core.logging_config import get_logger, is_prompt_trace_enabled
from app.middleware.registry import build_agent_middlewares

DEFAULT_AGENT_MODEL = "gpt-4o-mini"
DEFAULT_SYSTEM_PROMPT = get_default_agent_system_prompt()
DEFAULT_PROMPT_VARIANT = "quality_structured"
FALLBACK_EMPTY_RESPONSE = "응답을 생성하지 못했습니다. 다시 시도해 주세요."

logger = get_logger(__name__)


def is_openai_key_configured() -> bool:
    """
    기본 채팅 모델 provider의 API 키가 런타임 환경에 설정되어 있는지 확인한다.

    Returns:
        선택된 모델 provider 키가 설정되어 있으면 True
    """
    model_name = resolve_env_model(
        primary_env="MOLDUBOT_AGENT_MODEL",
        fallback_envs=("DEFAULT_CHAT_MODEL",),
        default_model=DEFAULT_AGENT_MODEL,
    )
    return is_model_provider_configured(model_name=model_name)


def _extract_latest_tool_payload(result: object, user_message: str = "") -> dict[str, Any]:
    """
    테스트/호환 목적의 최신 tool payload 추출 래퍼.

    Args:
        result: graph invoke 결과 객체
        user_message: 사용자 입력 원문

    Returns:
        추출된 tool payload
    """
    return extract_latest_tool_payload(result=result, user_message=user_message)


def _resolve_thread_id(thread_id: str | None) -> str:
    """
    테스트/호환 목적의 thread_id 정규화 래퍼.

    Args:
        thread_id: 외부에서 전달된 스레드 식별자

    Returns:
        정규화된 스레드 식별자
    """
    return resolve_thread_id(thread_id=thread_id)


class DeepChatAgent:
    """
    단일 deep agent를 생성해 사용자 메시지에 대한 응답을 반환하는 서비스 클래스.
    """

    def __init__(
        self,
        model_name: str,
        system_prompt: str,
        checkpointer: InMemorySaver | None = None,
    ) -> None:
        """
        Deep agent를 초기화한다.

        Args:
            model_name: OpenAI 모델 이름
            system_prompt: 에이전트 기본 시스템 프롬프트
        """
        self._graph = create_deep_agent(
            model=model_name,
            tools=get_agent_tools(),
            system_prompt=system_prompt,
            middleware=build_agent_middlewares(),
            subagents=get_agent_subagents(),
            skills=resolve_agent_skills_paths() or None,
            checkpointer=checkpointer or _get_agent_checkpointer(DEFAULT_PROMPT_VARIANT),
            name="moldubot-chat-agent",
        )
        self._last_tool_payload_ctx: ContextVar[dict[str, Any]] = ContextVar(
            "deep_agent_last_tool_payload",
            default={},
        )
        self._last_assistant_answer_ctx: ContextVar[str] = ContextVar(
            "deep_agent_last_assistant_answer",
            default="",
        )
        self._last_raw_model_output_ctx: ContextVar[str] = ContextVar(
            "deep_agent_last_raw_model_output",
            default="",
        )
        self._last_raw_model_content_ctx: ContextVar[Any] = ContextVar(
            "deep_agent_last_raw_model_content",
            default="",
        )

    def respond(self, user_message: str, thread_id: str | None = None) -> str:
        """
        사용자 메시지를 deep agent로 처리해 텍스트 응답을 반환한다.

        Args:
            user_message: 사용자 입력 문장
            thread_id: LangGraph short-term memory 스레드 식별자

        Returns:
            모델 응답 텍스트. 비어 있으면 기본 안내 문구 반환
        """
        turn_result = self.execute_turn(user_message=user_message, thread_id=thread_id)
        if turn_result.get("status") == "interrupted":
            return str(turn_result.get("answer") or "").strip() or "승인 후 실행할 수 있습니다."
        answer = str(turn_result.get("answer") or "").strip()
        self._last_assistant_answer_ctx.set(answer)
        return answer or FALLBACK_EMPTY_RESPONSE

    def execute_turn(self, user_message: str, thread_id: str | None = None) -> dict[str, Any]:
        """
        사용자 입력 1턴을 실행하고 완료/인터럽트 상태를 반환한다.

        Args:
            user_message: 사용자 입력 문장
            thread_id: LangGraph short-term memory 스레드 식별자

        Returns:
            실행 결과 사전
        """
        normalized_thread_id = resolve_thread_id(thread_id=thread_id)
        logger.info(
            "deep agent 응답 생성 시작: input_length=%s thread_id=%s",
            len(user_message),
            normalized_thread_id,
        )
        payload = {"messages": [{"role": "user", "content": user_message.strip()}]}
        result = self._invoke_graph(
            payload=payload,
            thread_id=normalized_thread_id,
        )
        return self._build_turn_response(
            result=result,
            thread_id=normalized_thread_id,
            user_message=user_message,
        )

    def resume_pending_actions(
        self,
        thread_id: str,
        approved: bool,
        confirm_token: str | None = None,
    ) -> dict[str, Any]:
        """
        HIL 인터럽트 대기중인 tool 호출을 승인/거절로 재개한다.

        Args:
            thread_id: 대화 스레드 식별자
            approved: 승인 여부
            confirm_token: 인터럽트 토큰(선택)

        Returns:
            재개 실행 결과 사전
        """
        normalized_thread_id = resolve_thread_id(thread_id=thread_id)
        decisions = self._build_resume_decisions(
            thread_id=normalized_thread_id,
            approved=approved,
            confirm_token=confirm_token,
        )
        if not decisions:
            return {
                "status": "failed",
                "thread_id": normalized_thread_id,
                "answer": "승인 대기 중인 작업을 찾지 못했습니다.",
                "interrupts": [],
            }
        result = self._invoke_graph(
            payload=Command(resume={"decisions": decisions}),
            thread_id=normalized_thread_id,
        )
        return self._build_turn_response(result=result, thread_id=normalized_thread_id)

    def get_last_tool_payload(self) -> dict[str, Any]:
        """
        마지막 agent 실행에서 수집한 tool payload를 반환한다.

        Returns:
            마지막 tool payload 사전
        """
        payload = self._last_tool_payload_ctx.get()
        if not isinstance(payload, dict):
            return {}
        return dict(payload)

    def get_last_assistant_answer(self) -> str:
        """
        마지막 agent 실행에서 수집한 최종 assistant 답변을 반환한다.

        Returns:
            후처리 완료된 마지막 assistant 답변 문자열
        """
        answer = self._last_assistant_answer_ctx.get()
        return str(answer or "").strip()

    def get_last_raw_model_output(self) -> str:
        """
        마지막 agent 실행에서 수집한 모델 직출력(raw)을 반환한다.

        Returns:
            후처리 적용 전 모델 직출력 문자열
        """
        output = self._last_raw_model_output_ctx.get()
        return str(output or "").strip()

    def get_last_raw_model_content(self) -> Any:
        """
        마지막 agent 실행에서 수집한 모델 content 원본 스냅샷을 반환한다.

        Returns:
            모델 content 스냅샷(문자열/리스트/딕셔너리 등)
        """
        return self._last_raw_model_content_ctx.get()

    def _invoke_graph(self, payload: dict[str, Any] | Command, thread_id: str) -> Mapping[str, Any] | object:
        """
        내부 graph invoke를 공통 실행한다.

        Args:
            payload: graph 입력 페이로드
            thread_id: 스레드 식별자

        Returns:
            graph invoke 결과 객체
        """
        if is_prompt_trace_enabled():
            logger.info("prompt_trace.agent_invoke_payload: %s", payload)
        return self._graph.invoke(payload, config={"configurable": {"thread_id": thread_id}})

    def _build_turn_response(self, result: object, thread_id: str, user_message: str = "") -> dict[str, Any]:
        """
        graph 실행 결과를 API 친화적인 사전으로 변환한다.

        Args:
            result: graph invoke 결과
            thread_id: 스레드 식별자
            user_message: 사용자 입력 원문(없으면 빈 문자열)

        Returns:
            상태/응답/인터럽트 정보를 담은 결과 사전
        """
        self._last_tool_payload_ctx.set(
            extract_latest_tool_payload(
                result=result,
                user_message=user_message,
            )
        )
        self._last_raw_model_output_ctx.set(_extract_raw_model_output(result=result))
        self._last_raw_model_content_ctx.set(_extract_raw_model_content(result=result))
        if not isinstance(result, Mapping):
            logger.warning("deep agent 결과 형식이 예상과 달라 기본 응답을 반환합니다.")
            answer = FALLBACK_EMPTY_RESPONSE
            self._last_assistant_answer_ctx.set(answer)
            return {"status": "failed", "thread_id": thread_id, "answer": answer, "interrupts": []}

        interrupts = extract_interrupt_requests(result=result)
        if interrupts:
            answer = "회의실/일정/ToDo 실행 전 승인 확인이 필요합니다."
            self._last_assistant_answer_ctx.set(answer)
            return {
                "status": "interrupted",
                "thread_id": thread_id,
                "answer": answer,
                "interrupts": interrupts,
            }

        answer = extract_assistant_text(result).strip()
        self._last_assistant_answer_ctx.set(answer)
        if is_prompt_trace_enabled():
            logger.info("prompt_trace.agent_final_answer: %s", answer)
        logger.info("deep agent 응답 생성 완료: answer_length=%s", len(answer))
        return {
            "status": "completed",
            "thread_id": thread_id,
            "answer": answer or FALLBACK_EMPTY_RESPONSE,
            "interrupts": [],
        }

    def _build_resume_decisions(
        self,
        thread_id: str,
        approved: bool,
        confirm_token: str | None,
    ) -> list[dict[str, Any]]:
        """
        현재 스레드 인터럽트 상태를 읽어 resume decisions payload를 구성한다.

        Args:
            thread_id: 스레드 식별자
            approved: 승인 여부
            confirm_token: 인터럽트 토큰

        Returns:
            Decision 목록
        """
        state = self._graph.get_state(config={"configurable": {"thread_id": thread_id}})
        pending_interrupts = list(getattr(state, "interrupts", ()) or []) if state is not None else []
        if not pending_interrupts:
            return []
        token = str(confirm_token or "").strip()
        selected_interrupts = pending_interrupts
        if token:
            matched_interrupts = [
                interrupt
                for interrupt in pending_interrupts
                if str(getattr(interrupt, "id", "") or "").strip() == token
            ]
            if matched_interrupts:
                selected_interrupts = matched_interrupts
            elif len(pending_interrupts) == 1:
                logger.warning("resume confirm_token mismatch fallback: token=%s", token)
            else:
                return []
        decisions: list[dict[str, Any]] = []
        for interrupt in selected_interrupts:
            value = getattr(interrupt, "value", None)
            if not isinstance(value, dict):
                continue
            action_requests = value.get("action_requests")
            if not isinstance(action_requests, list):
                continue
            for _ in action_requests:
                if approved:
                    decisions.append({"type": "approve"})
                else:
                    decisions.append({"type": "reject", "message": "사용자가 요청을 취소했습니다."})
        return decisions

    def _build_turn_response_from_state(self, thread_id: str, user_message: str = "") -> dict[str, Any]:
        """
        graph state 스냅샷으로 최종 턴 응답을 구성한다.

        Args:
            thread_id: 스레드 식별자
            user_message: 사용자 원문

        Returns:
            상태/응답/인터럽트 정보를 담은 결과 사전
        """
        state = self._graph.get_state(config={"configurable": {"thread_id": thread_id}})
        values = getattr(state, "values", None) if state is not None else None
        result = values if isinstance(values, Mapping) else {}
        self._last_tool_payload_ctx.set(
            extract_latest_tool_payload(
                result=result,
                user_message=user_message,
            )
        )
        self._last_raw_model_output_ctx.set(_extract_raw_model_output(result=result))
        self._last_raw_model_content_ctx.set(_extract_raw_model_content(result=result))
        state_interrupts = list(getattr(state, "interrupts", ()) or []) if state is not None else []
        if state_interrupts:
            interrupts = extract_interrupt_requests_from_state(state_interrupts=state_interrupts)
            answer = "회의실/일정/ToDo 실행 전 승인 확인이 필요합니다."
            self._last_assistant_answer_ctx.set(answer)
            return {
                "status": "interrupted",
                "thread_id": thread_id,
                "answer": answer,
                "interrupts": interrupts,
            }
        answer = extract_assistant_text(result).strip()
        self._last_assistant_answer_ctx.set(answer)
        if is_prompt_trace_enabled():
            logger.info("prompt_trace.agent_final_answer: %s", answer)
        logger.info("deep agent 스트리밍 응답 생성 완료: answer_length=%s", len(answer))
        return {
            "status": "completed",
            "thread_id": thread_id,
            "answer": answer or FALLBACK_EMPTY_RESPONSE,
            "interrupts": [],
        }


def _extract_raw_model_output(result: object) -> str:
    """
    graph 결과에서 after_model 단계가 저장한 모델 직출력 문자열을 추출한다.

    Args:
        result: graph invoke/state 결과

    Returns:
        모델 직출력 문자열. 없으면 빈 문자열
    """
    if not isinstance(result, Mapping):
        return ""
    value = result.get("raw_model_output")
    return str(value or "").strip()


def _extract_raw_model_content(result: object) -> Any:
    """
    graph 결과에서 모델 content 원본 스냅샷을 추출한다.

    Args:
        result: graph invoke/state 결과

    Returns:
        모델 content 스냅샷. 없으면 빈 문자열
    """
    if not isinstance(result, Mapping):
        return ""
    return result.get("raw_model_content", "")


@lru_cache(maxsize=16)
def _get_agent_checkpointer(prompt_variant: str) -> InMemorySaver:
    """
    에이전트 전역에서 재사용할 in-memory checkpointer를 반환한다.

    Returns:
        재사용 가능한 InMemorySaver 인스턴스
    """
    del prompt_variant
    return InMemorySaver()


@lru_cache(maxsize=8)
def get_deep_chat_agent(prompt_variant: str | None = None) -> DeepChatAgent:
    """
    애플리케이션 전역에서 재사용할 단일 deep agent 인스턴스를 반환한다.

    Returns:
        초기화된 DeepChatAgent 객체
    """
    normalized_model = resolve_env_model(
        primary_env="MOLDUBOT_AGENT_MODEL",
        fallback_envs=("DEFAULT_CHAT_MODEL",),
        default_model=DEFAULT_AGENT_MODEL,
    )
    prompt_override = str(os.getenv("MOLDUBOT_AGENT_SYSTEM_PROMPT", "")).strip()
    runtime_prompt_variant = str(prompt_variant or "").strip()
    env_prompt_variant = str(os.getenv("MOLDUBOT_AGENT_PROMPT_VARIANT", DEFAULT_PROMPT_VARIANT)).strip()
    selected_prompt_variant = runtime_prompt_variant or env_prompt_variant
    selected_variant_prompt = get_agent_system_prompt(selected_prompt_variant)
    normalized_prompt = prompt_override or selected_variant_prompt or DEFAULT_SYSTEM_PROMPT
    logger.info(
        "deep agent 초기화 설정: model=%s prompt_variant=%s override=%s",
        normalized_model,
        selected_prompt_variant or DEFAULT_PROMPT_VARIANT,
        bool(prompt_override),
    )
    checkpointer_key = selected_prompt_variant or DEFAULT_PROMPT_VARIANT
    return DeepChatAgent(
        model_name=normalized_model,
        system_prompt=normalized_prompt,
        checkpointer=_get_agent_checkpointer(checkpointer_key),
    )
