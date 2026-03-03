from __future__ import annotations

import time
from pathlib import Path
from typing import Any, Callable

from openai import OpenAIError

from app.agents.deep_chat_agent import FALLBACK_EMPTY_RESPONSE, get_deep_chat_agent, is_openai_key_configured
from app.agents.intent_parser import get_intent_parser
from app.agents.intent_schema import ExecutionStep, IntentDecomposition, IntentTaskType
from app.agents.tools import clear_current_mail, prime_current_mail
from app.api.answer_format_metadata import build_answer_format_metadata
from app.api.contracts import ChatRequest
from app.api.current_mail_pipeline import is_current_mail_query
from app.api.followup_scope import (
    apply_scope_instruction,
    build_scope_clarification,
    parse_requested_scope,
    remember_followup_search_result,
    resolve_effective_scope,
)
from app.api.search_chat_metadata import (
    build_evidence_mail_item,
    extract_aggregated_summary_from_tool_payload,
    extract_evidence_from_tool_payload,
    extract_tool_action,
    read_agent_final_answer,
    read_agent_tool_payload,
)
from app.api.search_chat_stream_utils import resolve_thread_id
from app.core.logging_config import get_logger
from app.core.metrics import get_chat_metrics_tracker
from app.services.intent_taxonomy_config import get_intent_taxonomy
from app.services.mail_context_service import build_mail_context_service
from app.services.next_action_recommender import recommend_next_actions
from app.services.web_source_search_service import search_web_sources, should_search_web_sources

logger = get_logger(__name__)
chat_metrics = get_chat_metrics_tracker()
ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"
mail_context_service = build_mail_context_service(db_path=MAIL_DB_PATH)
INTENT_CLARIFICATION_CONFIDENCE_THRESHOLD = 0.6


def is_non_action_query_for_interrupt_retry(
    decomposition: IntentDecomposition,
    user_message: str,
) -> bool:
    """인터럽트 자동 정리 후 재시도 가능한 비-실행 질의인지 판별한다."""
    action_steps = {ExecutionStep.BOOK_MEETING_ROOM, ExecutionStep.BOOK_CALENDAR_EVENT}
    has_action_step = any(step in action_steps for step in decomposition.steps)
    if decomposition.task_type == IntentTaskType.ACTION or has_action_step:
        return False
    query = str(user_message or "").strip()
    action_keywords = ("예약", "등록", "생성", "실행", "승인", "확정")
    return not any(keyword in query for keyword in action_keywords)


def run_search_chat(
    payload: ChatRequest,
    log_prefix: str,
    token_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """`/search/chat`과 `/search/chat/stream` 공통 처리 로직을 실행한다."""
    started_at = time.perf_counter()
    text = str(payload.message or "").strip()
    thread_id = resolve_thread_id(payload=payload)
    preview = (text[:80] + "...") if len(text) > 80 else text
    logger.info(
        "%s 요청 수신: length=%s preview=%s thread_id=%s",
        log_prefix,
        len(text),
        preview,
        thread_id,
    )
    selected_email_id = str(payload.email_id or "").strip()
    requested_scope = parse_requested_scope(runtime_options=payload.runtime_options)
    logger.info(
        "%s 선택 메일 식별자 수신: email_id=%s message_id=%s mailbox_user=%s",
        log_prefix,
        selected_email_id,
        selected_email_id,
        str(payload.mailbox_user or "").strip(),
    )
    runtime_options = payload.runtime_options if isinstance(payload.runtime_options, dict) else {}
    is_meeting_room_hil = bool(runtime_options.get("meeting_room_hil"))

    selected_message_id = "" if is_meeting_room_hil else selected_email_id
    intent_decomposition = parse_intent_decomposition_safely(user_message=text)
    scope_clarification = build_scope_clarification(
        user_message=text,
        requested_scope=requested_scope,
        thread_id=thread_id,
        selected_mail_available=bool(selected_message_id),
    )
    if scope_clarification is not None:
        logger.info(
            "%s 범위 확인 필요: thread_id=%s options=%s",
            log_prefix,
            thread_id,
            len(scope_clarification.get("options", [])),
        )
        return {
            "status": "needs_clarification",
            "thread_id": thread_id,
            "answer": str(scope_clarification.get("question") or "질문의 범위를 선택해 주세요."),
            "metadata": {
                "source": "scope-clarification",
                "evidence_mails": [],
                "aggregated_summary": [],
                "search_result_count": None,
                "resolved_scope": "",
                "clarification": scope_clarification,
                "answer_format": build_answer_format_metadata(
                    user_message=text,
                    answer=str(scope_clarification.get("question") or "질문의 범위를 선택해 주세요."),
                    status="needs_clarification",
                ),
            },
        }
    intent_clarification = build_intent_clarification(
        user_message=text,
        thread_id=thread_id,
        decomposition=intent_decomposition,
        runtime_options=runtime_options,
    )
    if intent_clarification is not None:
        logger.info(
            "%s 의도 확인 필요: thread_id=%s confidence=%.2f",
            log_prefix,
            thread_id,
            intent_decomposition.confidence if intent_decomposition is not None else -1.0,
        )
        question = str(intent_clarification.get("question") or "요청 의도를 한 번만 확인해 주세요.")
        return {
            "status": "needs_clarification",
            "thread_id": thread_id,
            "answer": question,
            "metadata": {
                "source": "intent-clarification",
                "evidence_mails": [],
                "aggregated_summary": [],
                "search_result_count": None,
                "resolved_scope": "",
                "clarification": intent_clarification,
                "answer_format": build_answer_format_metadata(
                    user_message=text,
                    answer=question,
                    status="needs_clarification",
                ),
            },
        }

    resolved_scope = resolve_effective_scope(user_message=text, requested_scope=requested_scope)
    evidence_mails: list[dict[str, str]] = []
    aggregated_summary: list[str] = []
    search_result_count: int | None = None
    tool_payload: dict[str, Any] = {}
    did_clear_current_mail = False
    if not selected_message_id and is_current_mail_query(text=text):
        clear_current_mail()
        did_clear_current_mail = True
        logger.warning("%s 선택 메일 식별자 누락: deep-agent 단일 경로로 진행", log_prefix)

    if selected_message_id:
        mailbox_user = str(payload.mailbox_user or "").strip()
        context_result = mail_context_service.get_mail_context(
            message_id=selected_message_id,
            mailbox_user=mailbox_user,
        )
        if context_result.mail is not None:
            prime_current_mail(mail=context_result.mail)
            evidence_mails = [
                build_evidence_mail_item(
                    message_id=context_result.mail.message_id,
                    subject=context_result.mail.subject,
                    received_date=context_result.mail.received_date,
                    from_address=context_result.mail.from_address,
                    web_link=context_result.mail.web_link,
                )
            ]
        else:
            clear_current_mail()
            did_clear_current_mail = True
        logger.info(
            "%s 선택 메일 컨텍스트 조회: message_id=%s status=%s source=%s",
            log_prefix,
            selected_message_id,
            context_result.status,
            context_result.source,
        )
        if context_result.mail is None:
            logger.warning("%s 선택 메일 컨텍스트 조회 실패: deep-agent 단일 경로로 진행", log_prefix)

    if not text:
        answer = "요청 내용을 입력해 주세요."
        source = "validation"
        success = False
        logger.info("%s 검증 실패: 빈 입력", log_prefix)
    elif not is_openai_key_configured():
        answer = "서버에 OPENAI_API_KEY가 설정되지 않아 답변을 생성할 수 없습니다."
        source = "missing-openai-key"
        success = False
        logger.warning("%s 환경 누락: OPENAI_API_KEY 미설정", log_prefix)
    else:
        source = "deep-agent"
        success = True
        try:
            prompt_variant = select_prompt_variant_from_intent(decomposition=intent_decomposition)
            agent = get_deep_chat_agent(prompt_variant=prompt_variant)
            scoped_message = apply_scope_instruction(
                user_message=text,
                resolved_scope=resolved_scope,
                thread_id=thread_id,
            )
            stream_execute_turn = getattr(agent, "stream_execute_turn", None)
            if callable(token_callback) and callable(stream_execute_turn):
                turn_result = stream_execute_turn(
                    user_message=scoped_message,
                    thread_id=thread_id,
                    on_token=token_callback,
                )
            else:
                turn_result = execute_agent_turn(agent=agent, user_message=scoped_message, thread_id=thread_id)
            turn_status = str(turn_result.get("status") or "").strip()
            if turn_status == "interrupted" and is_non_action_query_for_interrupt_retry(
                decomposition=intent_decomposition,
                user_message=text,
            ):
                logger.info("%s 비-실행 질의 인터럽트 자동 정리 후 재시도", log_prefix)
                agent.resume_pending_actions(
                    thread_id=thread_id,
                    approved=False,
                    confirm_token=None,
                )
                stream_execute_turn = getattr(agent, "stream_execute_turn", None)
                if callable(token_callback) and callable(stream_execute_turn):
                    turn_result = stream_execute_turn(
                        user_message=scoped_message,
                        thread_id=thread_id,
                        on_token=token_callback,
                    )
                else:
                    turn_result = execute_agent_turn(agent=agent, user_message=scoped_message, thread_id=thread_id)
                turn_status = str(turn_result.get("status") or "").strip()

            if turn_status == "interrupted":
                answer = str(turn_result.get("answer") or "").strip() or "승인 후 실행할 수 있습니다."
                response_payload = {
                    "status": "pending_approval",
                    "thread_id": thread_id,
                    "answer": answer,
                    "metadata": {
                        "source": "deep-agent-hitl",
                        "evidence_mails": evidence_mails,
                        "aggregated_summary": aggregated_summary,
                        "search_result_count": search_result_count,
                        "resolved_scope": resolved_scope,
                        "confirm": build_hitl_confirm_metadata(
                            interrupts=turn_result.get("interrupts"),
                            thread_id=thread_id,
                        ),
                        "answer_format": build_answer_format_metadata(
                            user_message=text,
                            answer=answer,
                            status="pending_approval",
                        ),
                    },
                }
                if selected_message_id and not did_clear_current_mail:
                    clear_current_mail()
                elapsed_ms = (time.perf_counter() - started_at) * 1000
                chat_metrics.record(
                    source="deep-agent-hitl",
                    success=True,
                    elapsed_ms=elapsed_ms,
                    is_fallback=False,
                )
                metadata = response_payload.get("metadata")
                if isinstance(metadata, dict):
                    metadata["elapsed_ms"] = round(elapsed_ms, 1)
                return response_payload

            answer = str(turn_result.get("answer") or "").strip() or FALLBACK_EMPTY_RESPONSE
            tool_payload = read_agent_tool_payload(agent=agent)
            answer = read_agent_final_answer(agent=agent) or answer
            if not answer:
                answer = FALLBACK_EMPTY_RESPONSE
            tool_action = extract_tool_action(tool_payload=tool_payload)
            tool_evidence = extract_evidence_from_tool_payload(tool_payload=tool_payload)
            if tool_action == "mail_search":
                evidence_mails = tool_evidence
                raw_results = tool_payload.get("results") if isinstance(tool_payload, dict) else None
                if isinstance(raw_results, list):
                    search_result_count = len(raw_results)
                else:
                    raw_count = tool_payload.get("count") if isinstance(tool_payload, dict) else None
                    if isinstance(raw_count, int):
                        search_result_count = raw_count
            elif tool_evidence:
                evidence_mails = tool_evidence
            aggregated_summary = extract_aggregated_summary_from_tool_payload(tool_payload=tool_payload)
            if tool_action == "mail_search":
                remember_followup_search_result(
                    thread_id=thread_id,
                    search_result_count=search_result_count,
                )
            logger.info("%s 처리 완료: source=%s answer_length=%s", log_prefix, source, len(answer))
        except OpenAIError as exc:
            logger.error("%s OpenAI 호출 실패: %s", log_prefix, exc)
            answer = "OpenAI 호출에 실패했습니다. 잠시 후 다시 시도해 주세요."
            source = "openai-error"
            success = False
        except Exception as exc:
            logger.exception("%s 처리 중 내부 오류: %s", log_prefix, exc)
            answer = "요청 처리 중 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            source = "internal-error"
            success = False

    elapsed_ms = (time.perf_counter() - started_at) * 1000
    is_fallback = answer.strip() == FALLBACK_EMPTY_RESPONSE
    chat_metrics.record(source=source, success=success, elapsed_ms=elapsed_ms, is_fallback=is_fallback)
    logger.info(
        "%s 메트릭 기록: source=%s success=%s fallback=%s elapsed_ms=%.1f",
        log_prefix,
        source,
        success,
        is_fallback,
        elapsed_ms,
    )
    if selected_message_id and not did_clear_current_mail:
        clear_current_mail()

    next_actions = recommend_next_actions(
        user_message=text,
        answer=answer,
        tool_payload=tool_payload,
        intent_task_type=intent_decomposition.task_type.value if intent_decomposition is not None else "",
        intent_output_format=intent_decomposition.output_format.value if intent_decomposition is not None else "",
    )
    web_sources: list[dict[str, str]] = []
    if should_search_web_sources(
        user_message=text,
        intent_task_type=intent_decomposition.task_type.value if intent_decomposition is not None else "",
    ):
        web_sources = search_web_sources(user_message=text)

    return {
        "status": "completed",
        "thread_id": thread_id,
        "answer": answer,
        "metadata": {
            "source": source,
            "evidence_mails": evidence_mails,
            "aggregated_summary": aggregated_summary,
            "search_result_count": search_result_count,
            "resolved_scope": resolved_scope,
            "elapsed_ms": round(elapsed_ms, 1),
            "answer_format": build_answer_format_metadata(
                user_message=text,
                answer=answer,
                status="completed",
            ),
            "intent_task_type": intent_decomposition.task_type.value if intent_decomposition is not None else "",
            "intent_output_format": intent_decomposition.output_format.value if intent_decomposition is not None else "",
            "intent_confidence": round(intent_decomposition.confidence, 2) if intent_decomposition is not None else 0.0,
            "next_actions": next_actions,
            "web_sources": web_sources,
        },
    }


def parse_intent_decomposition_safely(user_message: str) -> IntentDecomposition | None:
    """라우팅 보조용 intent 구조분해를 안전하게 파싱한다."""
    normalized = str(user_message or "").strip()
    if not normalized:
        return None
    try:
        return get_intent_parser().parse(user_message=normalized)
    except Exception as exc:
        logger.warning("intent 구조분해 파싱 실패: %s", exc)
        return None


def select_prompt_variant_from_intent(decomposition: IntentDecomposition | None) -> str:
    """intent task 유형 기반으로 에이전트 prompt variant를 선택한다."""
    if decomposition is None:
        return "quality_structured"
    task_type = decomposition.task_type
    if task_type in (IntentTaskType.ANALYSIS, IntentTaskType.SOLUTION):
        return "quality_structured"
    if task_type == IntentTaskType.RETRIEVAL:
        return "fast_compact"
    return "quality_structured"


def build_intent_clarification(
    user_message: str,
    thread_id: str,
    decomposition: IntentDecomposition | None,
    runtime_options: dict[str, Any],
) -> dict[str, Any] | None:
    """low-confidence 의도에 대해 확인 질문 메타데이터를 구성한다."""
    if decomposition is None:
        return None
    if bool(runtime_options.get("skip_intent_clarification")):
        return None
    if str(runtime_options.get("scope") or "").strip():
        return None
    if is_explicit_todo_registration_query(user_message=user_message):
        return None
    if any(
        step in decomposition.steps
        for step in (
            ExecutionStep.BOOK_MEETING_ROOM,
            ExecutionStep.BOOK_CALENDAR_EVENT,
            ExecutionStep.SEARCH_MEETING_SCHEDULE,
        )
    ):
        return None
    if decomposition.confidence >= INTENT_CLARIFICATION_CONFIDENCE_THRESHOLD:
        return None
    compact = str(user_message or "").replace(" ", "")
    if any(token in compact for token in ("요약", "정리", "조회", "검색")):
        return None
    question = (
        "요청 의도를 확인할게요. 현재메일 기준으로 "
        "1) 요약 2) 원인 분석 3) 해결 방법 중 무엇을 원하시나요?"
    )
    return {
        "required": True,
        "thread_id": thread_id,
        "kind": "intent",
        "task_type": decomposition.task_type.value,
        "confidence": round(decomposition.confidence, 2),
        "question": question,
    }


def is_explicit_todo_registration_query(user_message: str) -> bool:
    """사용자 입력이 ToDo 등록 실행 의도인지 판별한다."""
    compact = str(user_message or "").replace(" ", "").lower()
    if not compact:
        return False
    policy = get_intent_taxonomy().recipient_todo_policy
    has_todo = any(token in compact for token in policy.todo_tokens)
    has_registration = any(token in compact for token in policy.registration_tokens)
    return has_todo and has_registration


def build_hitl_confirm_metadata(interrupts: object, thread_id: str) -> dict[str, Any]:
    """HIL 인터럽트 결과를 UI 확인 카드 메타데이터로 변환한다."""
    normalized_interrupts = interrupts if isinstance(interrupts, list) else []
    first_interrupt = normalized_interrupts[0] if normalized_interrupts else {}
    first_actions = first_interrupt.get("actions") if isinstance(first_interrupt, dict) else []
    confirm_token = first_interrupt.get("interrupt_id") if isinstance(first_interrupt, dict) else ""
    actions = first_actions if isinstance(first_actions, list) else []
    return {
        "required": True,
        "thread_id": thread_id,
        "confirm_token": str(confirm_token or "").strip(),
        "actions": actions,
    }


def execute_agent_turn(agent: Any, user_message: str, thread_id: str) -> dict[str, Any]:
    """agent 실행 인터페이스 호환 래퍼(`execute_turn` 우선, `respond` fallback)."""
    execute_turn = getattr(agent, "execute_turn", None)
    if callable(execute_turn):
        result = execute_turn(user_message=user_message, thread_id=thread_id)
        if isinstance(result, dict):
            return result
    respond = getattr(agent, "respond", None)
    if callable(respond):
        answer = str(respond(user_message=user_message, thread_id=thread_id) or "").strip() or FALLBACK_EMPTY_RESPONSE
        return {"status": "completed", "answer": answer, "thread_id": thread_id, "interrupts": []}
    return {"status": "failed", "answer": FALLBACK_EMPTY_RESPONSE, "thread_id": thread_id, "interrupts": []}
