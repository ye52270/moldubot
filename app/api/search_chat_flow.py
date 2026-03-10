from __future__ import annotations
import time
from pathlib import Path
from typing import Any, Callable
from app.agents.deep_chat_agent import FALLBACK_EMPTY_RESPONSE, get_deep_chat_agent, is_openai_key_configured
from app.agents.intent_parser import get_intent_parser
from app.agents.tools import clear_current_mail, prime_current_mail
from app.agents.tools import reset_search_scope_contract, set_search_scope_contract
from app.api.answer_format_metadata import build_answer_format_metadata
from app.api.contracts import ChatRequest
from app.api.current_mail_pipeline import (
    remember_sticky_current_mail,
    resolve_current_mail_mode,
)
from app.api.search_chat_flow_helpers import (
    _extract_overlap_tokens as _extract_overlap_tokens_impl,
    build_enrichment_payloads,
    build_scope_metadata,
    build_search_scope_contract,
    enrich_major_point_related_mails,
    resolve_web_sources_for_answer,
)
from app.api.search_chat_intent_helpers import (
    build_hitl_confirm_metadata,
    build_intent_clarification,
    execute_agent_turn,
    is_non_action_query_for_interrupt_retry,
    parse_intent_decomposition_safely,
    select_prompt_variant_from_intent,
)
from app.api.search_chat_response_builders import (
    build_intent_clarification_response,
    build_pending_approval_response,
    build_scope_clarification_response,
    build_web_search_direct_response,
)
from app.api.followup_scope import (
    apply_scope_instruction,
    build_scope_clarification,
    parse_requested_scope,
    remember_followup_search_result,
    resolve_default_scope,
    resolve_effective_scope,
)
from app.api.followup_reference import (
    build_followup_reference_hint,
    build_recent_context_hint,
    remember_recent_turn_context,
    remember_followup_reference,
)
from app.api.search_chat_metadata import (
    build_major_point_evidence,
    build_evidence_mail_item,
    extract_aggregated_summary_from_tool_payload,
    extract_evidence_from_tool_payload,
    extract_tool_action,
    read_agent_final_answer,
    read_agent_raw_model_content,
    read_agent_raw_model_output,
    read_agent_tool_payload,
)
from app.api.search_chat_next_actions_runtime import (
    ACTION_ID_SEARCH_RELATED_MAILS,
    ACTION_ID_WEB_SEARCH,
    normalize_next_action_id,
    resolve_forced_next_action_query,
    should_suppress_internal_mail_evidence,
)
from app.api.search_chat_stream_utils import resolve_thread_id
from app.core.logging_config import get_logger
from app.core.metrics import get_chat_metrics_tracker
from app.services.code_review_quality_service import refine_code_review_answer_with_metadata
from app.services.answer_postprocessor_contract_utils import parse_llm_response_contract
from app.services.answer_postprocessor_summary import is_current_mail_summary_request
from app.services.mail_context_service import build_mail_context_service
from app.services.mail_search_service import MailSearchService
from app.services.next_action_recommender import recommend_next_actions
from app.services.web_source_search_service import search_web_sources
logger = get_logger(__name__)
chat_metrics = get_chat_metrics_tracker()
ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"
mail_context_service = build_mail_context_service(db_path=MAIL_DB_PATH)
mail_search_service = MailSearchService(db_path=MAIL_DB_PATH)


def _build_selected_mail_evidence_snippet(selected_mail: Any) -> str:
    """
    선택 메일 근거 표시용 snippet을 생성한다.

    Args:
        selected_mail: 선택 메일 레코드

    Returns:
        요약/본문 기반 짧은 스니펫
    """
    summary_text = str(getattr(selected_mail, "summary_text", "") or "").strip()
    if summary_text:
        return summary_text[:280]
    body_text = str(getattr(selected_mail, "body_text", "") or "").strip()
    if body_text:
        compact = " ".join(body_text.split())
        if compact:
            return compact[:280]
    return str(getattr(selected_mail, "subject", "") or "").strip()


def _extract_overlap_tokens(text: str) -> set[str]:
    """
    테스트/호환 목적의 토큰 추출 래퍼를 제공한다.

    Args:
        text: 입력 텍스트

    Returns:
        겹침 판정용 토큰 집합
    """
    return _extract_overlap_tokens_impl(text=text)


def _use_fresh_agent_thread_for_current_mail_summary(
    user_message: str,
    resolved_scope: str,
    selected_message_id: str,
) -> bool:
    """
    현재메일 요약 요청일 때 누적 히스토리 편향 방지를 위해 fresh thread 사용 여부를 판단한다.

    Args:
        user_message: 사용자 입력
        resolved_scope: 최종 해석된 검색 범위

    Returns:
        fresh thread 사용 대상이면 True
    """
    compact = str(user_message or "").replace(" ", "")
    if str(resolved_scope or "").strip().lower() != "current_mail":
        return False
    if not str(selected_message_id or "").strip():
        return False
    return "현재메일" in compact and ("요약" in compact or "정리" in compact)


def _build_agent_thread_id(
    thread_id: str,
    selected_message_id: str,
    use_fresh_thread: bool,
) -> str:
    """
    agent 실행용 thread id를 구성한다.

    Args:
        thread_id: 기본 스레드 ID
        selected_message_id: 선택 메일 식별자
        use_fresh_thread: fresh thread 사용 여부

    Returns:
        agent 실행용 스레드 ID
    """
    if not use_fresh_thread:
        return str(thread_id or "").strip()
    mail_key = str(selected_message_id or "").strip()[:24] or "current_mail"
    return f"{thread_id}::cms::{mail_key}::{int(time.time() * 1000)}"


def _should_retry_current_mail_summary_json(
    user_message: str,
    resolved_scope: str,
    tool_payload: dict[str, Any],
    final_answer: str,
    raw_model_content: Any,
) -> bool:
    """
    현재메일 요약 응답에서 JSON 파싱 실패 시 1회 재요청 대상인지 판별한다.

    Args:
        user_message: 사용자 입력
        resolved_scope: 최종 해석된 범위
        raw_model_content: 모델 원문 content

    Returns:
        재요청 필요 시 True
    """
    if str(resolved_scope or "").strip().lower() != "current_mail":
        return False
    tool_action = str(tool_payload.get("action") or "").strip().lower() if isinstance(tool_payload, dict) else ""
    if tool_action != "current_mail":
        return False
    if not is_current_mail_summary_request(user_message=user_message):
        return False
    normalized_answer = str(final_answer or "").strip()
    looks_like_raw_json_answer = (
        normalized_answer.startswith("{")
        or normalized_answer.startswith("```json")
        or normalized_answer.startswith("```")
    )
    if not looks_like_raw_json_answer:
        return False
    return parse_llm_response_contract(raw_answer=raw_model_content, log_failures=False) is None
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
    is_current_mail_mode = resolve_current_mail_mode(
        user_message=text,
        thread_id=thread_id,
        selected_mail_available=bool(selected_email_id),
        requested_scope=requested_scope,
    )
    remember_sticky_current_mail(
        thread_id=thread_id,
        user_message=text,
        requested_scope=requested_scope,
        selected_mail_available=bool(selected_email_id),
        is_current_mail_mode=is_current_mail_mode,
    )
    preliminary_scope = resolve_effective_scope(user_message=text, requested_scope=requested_scope)
    logger.info(
        "%s 선택 메일 식별자 수신: email_id=%s message_id=%s mailbox_user=%s",
        log_prefix,
        selected_email_id,
        selected_email_id,
        str(payload.mailbox_user or "").strip(),
    )
    runtime_options = dict(payload.runtime_options) if isinstance(payload.runtime_options, dict) else {}
    next_action_id = normalize_next_action_id(runtime_options=runtime_options)
    preloaded_mail_context = None
    preloaded_mail_subject = ""
    preloaded_mail_from = ""
    if next_action_id:
        runtime_options["skip_intent_clarification"] = True
        if selected_email_id and next_action_id in {ACTION_ID_SEARCH_RELATED_MAILS, ACTION_ID_WEB_SEARCH}:
            preloaded_mail_context = mail_context_service.get_mail_context(
                message_id=selected_email_id,
                mailbox_user=str(payload.mailbox_user or "").strip(),
            )
            preloaded_mail = getattr(preloaded_mail_context, "mail", None)
            if preloaded_mail is not None:
                preloaded_mail_subject = str(getattr(preloaded_mail, "subject", "") or "").strip()
                preloaded_mail_from = str(getattr(preloaded_mail, "from_address", "") or "").strip()
        text = resolve_forced_next_action_query(
            next_action_id=next_action_id,
            fallback_query=text,
            current_mail_subject=preloaded_mail_subject,
            current_mail_from=preloaded_mail_from,
        )
    is_meeting_room_hil = bool(runtime_options.get("meeting_room_hil"))
    selected_message_id = "" if is_meeting_room_hil else selected_email_id
    intent_decomposition = parse_intent_decomposition_safely(user_message=text, parser_factory=get_intent_parser)
    scope_clarification = None
    if not next_action_id:
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
        scope_question = str(scope_clarification.get("question") or "질문의 범위를 선택해 주세요.")
        return build_scope_clarification_response(
            question=scope_question,
            clarification=scope_clarification,
            thread_id=thread_id,
            is_current_mail_mode=is_current_mail_mode,
            scope_metadata=build_scope_metadata(
                resolved_scope=preliminary_scope,
                is_current_mail_mode=is_current_mail_mode,
                selected_message_id=selected_message_id,
                thread_id=thread_id,
            ),
            build_answer_format_metadata=build_answer_format_metadata,
        )
    intent_clarification = build_intent_clarification(
        user_message=text,
        thread_id=thread_id,
        decomposition=intent_decomposition,
        runtime_options=runtime_options,
        is_current_mail_mode=is_current_mail_mode,
        selected_mail_available=bool(selected_message_id),
    )
    if intent_clarification is not None:
        logger.info(
            "%s 의도 확인 필요: thread_id=%s confidence=%.2f",
            log_prefix,
            thread_id,
            intent_decomposition.confidence if intent_decomposition is not None else -1.0,
        )
        question = str(intent_clarification.get("question") or "요청 의도를 한 번만 확인해 주세요.")
        return build_intent_clarification_response(
            question=question,
            clarification=intent_clarification,
            thread_id=thread_id,
            is_current_mail_mode=is_current_mail_mode,
            scope_metadata=build_scope_metadata(
                resolved_scope=preliminary_scope,
                is_current_mail_mode=is_current_mail_mode,
                selected_message_id=selected_message_id,
                thread_id=thread_id,
            ),
            build_answer_format_metadata=build_answer_format_metadata,
        )
    resolved_scope = resolve_effective_scope(user_message=text, requested_scope=requested_scope)
    if not resolved_scope:
        resolved_scope = resolve_default_scope(is_current_mail_mode=is_current_mail_mode)
    scope_metadata = build_scope_metadata(
        resolved_scope=resolved_scope,
        is_current_mail_mode=is_current_mail_mode,
        selected_message_id=selected_message_id,
        thread_id=thread_id,
    )
    scope_contract = build_search_scope_contract(
        user_message=text,
        resolved_scope=resolved_scope,
        intent_decomposition=intent_decomposition,
        is_current_mail_mode=is_current_mail_mode,
    )
    evidence_mails: list[dict[str, str]] = []
    aggregated_summary: list[str] = []
    search_result_count: int | None = None
    tool_payload: dict[str, Any] = {}
    code_review_quality: dict[str, Any] = {}
    did_clear_current_mail = False
    selected_mail = None
    if not selected_message_id and is_current_mail_mode:
        clear_current_mail()
        did_clear_current_mail = True
        logger.warning("%s 선택 메일 식별자 누락: deep-agent 단일 경로로 진행", log_prefix)
    if selected_message_id:
        mailbox_user = str(payload.mailbox_user or "").strip()
        context_result = preloaded_mail_context
        if context_result is None:
            context_result = mail_context_service.get_mail_context(
                message_id=selected_message_id,
                mailbox_user=mailbox_user,
            )
        if context_result.mail is not None:
            selected_mail = context_result.mail
            prime_current_mail(mail=context_result.mail)
            evidence_mails = [
                build_evidence_mail_item(
                    message_id=context_result.mail.message_id,
                    subject=context_result.mail.subject,
                    received_date=context_result.mail.received_date,
                    from_address=context_result.mail.from_address,
                    web_link=context_result.mail.web_link,
                    snippet=_build_selected_mail_evidence_snippet(context_result.mail),
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
    if next_action_id == ACTION_ID_WEB_SEARCH:
        mail_subject = str(getattr(selected_mail, "subject", "") or "").strip()
        mail_summary = str(getattr(selected_mail, "summary_text", "") or "").strip()
        web_direct_response = build_web_search_direct_response(
            user_message=text,
            thread_id=thread_id,
            is_current_mail_mode=is_current_mail_mode,
            resolved_scope=resolved_scope,
            selected_message_id=selected_message_id,
            did_clear_current_mail=did_clear_current_mail,
            clear_current_mail=clear_current_mail,
            build_answer_format_metadata=build_answer_format_metadata,
            selected_mail_subject=mail_subject,
            selected_mail_summary=mail_summary,
            search_web_sources_fn=search_web_sources,
        )
        metadata = web_direct_response.get("metadata")
        if isinstance(metadata, dict):
            metadata.update(scope_metadata)
            metadata["elapsed_ms"] = round((time.perf_counter() - started_at) * 1000, 1)
            metadata["intent_task_type"] = intent_decomposition.task_type.value if intent_decomposition is not None else ""
            metadata["intent_output_format"] = (
                intent_decomposition.output_format.value if intent_decomposition is not None else ""
            )
            metadata["intent_confidence"] = (
                round(intent_decomposition.confidence, 2) if intent_decomposition is not None else 0.0
            )
        return web_direct_response
    answer = ""
    raw_answer = ""
    raw_model_output = ""
    raw_model_content = ""
    tool_payload = {}
    agent_thread_id = thread_id
    if not text:
        answer = "요청 내용을 입력해 주세요."
        raw_answer = answer
        raw_model_output = answer
        raw_model_content = answer
        source = "validation"
        success = False
        logger.info("%s 검증 실패: 빈 입력", log_prefix)
    elif not is_openai_key_configured():
        answer = "서버에 선택된 LLM provider API 키가 설정되지 않아 답변을 생성할 수 없습니다."
        raw_answer = answer
        raw_model_output = answer
        raw_model_content = answer
        source = "missing-llm-key"
        success = False
        logger.warning("%s 환경 누락: LLM provider API key 미설정", log_prefix)
    else:
        source = "deep-agent"
        success = True
        scope_token: object | None = None
        try:
            scope_token = set_search_scope_contract(scope_contract)
            prompt_variant = select_prompt_variant_from_intent(
                decomposition=intent_decomposition,
                user_message=text,
                resolved_scope=resolved_scope,
            )
            agent = get_deep_chat_agent(prompt_variant=prompt_variant)
            use_fresh_thread = _use_fresh_agent_thread_for_current_mail_summary(
                user_message=text,
                resolved_scope=resolved_scope,
                selected_message_id=selected_message_id,
            )
            agent_thread_id = _build_agent_thread_id(
                thread_id=thread_id,
                selected_message_id=selected_message_id,
                use_fresh_thread=use_fresh_thread,
            )
            scoped_message = apply_scope_instruction(
                user_message=text,
                resolved_scope=resolved_scope,
                thread_id=thread_id,
            )
            recent_context_hint = build_recent_context_hint(
                thread_id=thread_id,
                user_message=text,
            )
            if recent_context_hint:
                logger.info("%s 최근 턴 문맥 힌트 주입: thread_id=%s", log_prefix, thread_id)
                scoped_message = f"{recent_context_hint}\n{scoped_message}"
            followup_reference_hint = build_followup_reference_hint(
                thread_id=thread_id,
                user_message=text,
                resolved_scope=resolved_scope,
                is_current_mail_mode=is_current_mail_mode,
            )
            if followup_reference_hint:
                logger.info("%s 후속 참조 문맥 힌트 주입: thread_id=%s", log_prefix, thread_id)
                scoped_message = f"{followup_reference_hint}\n{scoped_message}"
            stream_execute_turn = getattr(agent, "stream_execute_turn", None)
            if callable(token_callback) and callable(stream_execute_turn):
                turn_result = stream_execute_turn(
                    user_message=scoped_message,
                    thread_id=agent_thread_id,
                    on_token=token_callback,
                )
            else:
                turn_result = execute_agent_turn(agent=agent, user_message=scoped_message, thread_id=agent_thread_id)
            turn_status = str(turn_result.get("status") or "").strip()
            if turn_status == "interrupted" and is_non_action_query_for_interrupt_retry(
                decomposition=intent_decomposition,
                user_message=text,
            ):
                logger.info("%s 비-실행 질의 인터럽트 자동 정리 후 재시도", log_prefix)
                agent.resume_pending_actions(
                    thread_id=agent_thread_id,
                    approved=False,
                    confirm_token=None,
                )
                stream_execute_turn = getattr(agent, "stream_execute_turn", None)
                if callable(token_callback) and callable(stream_execute_turn):
                    turn_result = stream_execute_turn(
                        user_message=scoped_message,
                        thread_id=agent_thread_id,
                        on_token=token_callback,
                    )
                else:
                    turn_result = execute_agent_turn(
                        agent=agent,
                        user_message=scoped_message,
                        thread_id=agent_thread_id,
                    )
                turn_status = str(turn_result.get("status") or "").strip()
            if turn_status == "interrupted":
                answer = str(turn_result.get("answer") or "").strip() or "승인 후 실행할 수 있습니다."
                raw_answer = answer
                raw_model_output = read_agent_raw_model_output(agent=agent) or answer
                raw_model_content = read_agent_raw_model_content(agent=agent) or raw_model_output
                response_payload = build_pending_approval_response(
                    answer=answer,
                    thread_id=thread_id,
                    is_current_mail_mode=is_current_mail_mode,
                    evidence_mails=evidence_mails,
                    aggregated_summary=aggregated_summary,
                    search_result_count=search_result_count,
                    resolved_scope=resolved_scope,
                    scope_metadata=scope_metadata,
                    confirm_metadata=build_hitl_confirm_metadata(
                        interrupts=turn_result.get("interrupts"),
                        thread_id=agent_thread_id,
                    ),
                    build_answer_format_metadata=build_answer_format_metadata,
                    raw_model_output=raw_model_output,
                    raw_model_content=raw_model_content,
                )
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
            raw_answer = answer
            raw_model_output = read_agent_raw_model_output(agent=agent) or answer
            raw_model_content = read_agent_raw_model_content(agent=agent) or raw_model_output
            tool_payload = read_agent_tool_payload(agent=agent)
            answer = read_agent_final_answer(agent=agent) or answer
            raw_answer = str(answer or "").strip() or raw_answer
            if _should_retry_current_mail_summary_json(
                user_message=text,
                resolved_scope=resolved_scope,
                tool_payload=tool_payload,
                final_answer=answer,
                raw_model_content=raw_model_content,
            ):
                logger.info("%s current_mail_summary json_parse_retry: attempt=1", log_prefix)
                retry_message = (
                    "직전 결과를 다시 생성하세요. 반드시 JSON 객체 하나만 출력하세요. "
                    "코드펜스/설명/머리말 없이 raw JSON만 반환하세요."
                )
                stream_execute_turn = getattr(agent, "stream_execute_turn", None)
                if callable(token_callback) and callable(stream_execute_turn):
                    retry_result = stream_execute_turn(
                        user_message=retry_message,
                        thread_id=agent_thread_id,
                        on_token=token_callback,
                    )
                else:
                    retry_result = execute_agent_turn(
                        agent=agent,
                        user_message=retry_message,
                        thread_id=agent_thread_id,
                    )
                if str(retry_result.get("status") or "").strip() == "completed":
                    retried_answer = str(retry_result.get("answer") or "").strip()
                    retried_raw_output = read_agent_raw_model_output(agent=agent) or retried_answer
                    retried_raw_content = read_agent_raw_model_content(agent=agent) or retried_raw_output
                    if parse_llm_response_contract(
                        raw_answer=retried_raw_content,
                        log_failures=False,
                    ) is not None:
                        answer = retried_answer or answer
                        raw_answer = answer
                        raw_model_output = retried_raw_output
                        raw_model_content = retried_raw_content
                        tool_payload = read_agent_tool_payload(agent=agent) or tool_payload
                        logger.info("%s current_mail_summary json_parse_retry: success=true", log_prefix)
                    else:
                        logger.info("%s current_mail_summary json_parse_retry: success=false", log_prefix)
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
            answer, code_review_quality = refine_code_review_answer_with_metadata(
                user_message=text,
                answer=answer,
                tool_payload=tool_payload,
            )
            remember_recent_turn_context(
                thread_id=thread_id,
                resolved_scope=resolved_scope,
                evidence_mails=evidence_mails,
            )
            remember_followup_reference(
                thread_id=thread_id,
                user_message=text,
                answer=answer,
                resolved_scope=resolved_scope,
                is_current_mail_mode=is_current_mail_mode,
            )
            logger.info("%s 처리 완료: source=%s answer_length=%s", log_prefix, source, len(answer))
        except Exception as exc:
            logger.exception("%s 처리 중 내부 오류: %s", log_prefix, exc)
            answer = "LLM 호출 또는 내부 오류가 발생했습니다. 잠시 후 다시 시도해 주세요."
            raw_answer = answer
            raw_model_output = answer
            raw_model_content = answer
            source = "internal-error"
            success = False
        finally:
            if scope_token is not None:
                reset_search_scope_contract(scope_token)

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

    suppress_internal_evidence = should_suppress_internal_mail_evidence(next_action_id=next_action_id)
    if suppress_internal_evidence:
        evidence_mails = []

    next_actions = recommend_next_actions(
        user_message=text,
        answer=answer,
        tool_payload=tool_payload,
        intent_task_type=intent_decomposition.task_type.value if intent_decomposition is not None else "",
        intent_output_format=intent_decomposition.output_format.value if intent_decomposition is not None else "",
    )
    web_sources, web_verification_reasons = resolve_web_sources_for_answer(
        user_message=text,
        intent_task_type=intent_decomposition.task_type.value if intent_decomposition is not None else "",
        resolved_scope=resolved_scope,
        tool_payload=tool_payload,
        intent_confidence=intent_decomposition.confidence if intent_decomposition is not None else None,
        model_answer=answer,
        next_action_id=next_action_id,
    )
    if isinstance(code_review_quality, dict) and code_review_quality.get("enabled"):
        code_review_quality["web_source_count"] = len(web_sources)
        code_review_quality["has_sources"] = bool(web_sources)
    answer_format = build_answer_format_metadata(
        user_message=text,
        answer=answer,
        status="completed",
    )
    major_point_evidence = build_major_point_evidence(
        answer_format=answer_format,
        tool_payload=tool_payload,
        evidence_mails=evidence_mails,
    )
    if not suppress_internal_evidence:
        major_point_evidence = enrich_major_point_related_mails(
            rows=major_point_evidence,
            tool_payload=tool_payload,
            mail_search_service=mail_search_service,
        )
    _, _, _, context_enrichment, semantic_contract = build_enrichment_payloads(
        answer=answer,
        answer_format=answer_format,
        tool_payload=tool_payload,
        evidence_mails=evidence_mails,
        next_actions=next_actions,
        intent_confidence=float(intent_decomposition.confidence if intent_decomposition is not None else 0.0),
        web_sources=web_sources,
    )

    return {
        "status": "completed",
        "thread_id": thread_id,
        "answer": answer,
        "metadata": {
            "agent_thread_id": str(agent_thread_id or thread_id),
            "tool_action": extract_tool_action(tool_payload=tool_payload),
            "source": source,
            "raw_answer": raw_answer or answer,
            "raw_model_output": raw_model_output or raw_answer or answer,
            "raw_model_content": raw_model_content or raw_model_output or raw_answer or answer,
            "query_type": "current_mail" if is_current_mail_mode else "general",
            "evidence_mails": evidence_mails,
            "aggregated_summary": aggregated_summary,
            "search_result_count": search_result_count,
            "resolved_scope": resolved_scope,
            **scope_metadata,
            "elapsed_ms": round(elapsed_ms, 1),
            "answer_format": answer_format,
            "intent_task_type": intent_decomposition.task_type.value if intent_decomposition is not None else "",
            "intent_output_format": intent_decomposition.output_format.value if intent_decomposition is not None else "",
            "intent_confidence": round(intent_decomposition.confidence, 2) if intent_decomposition is not None else 0.0,
            "next_actions": next_actions,
            "web_sources": web_sources,
            "web_verification_reasons": web_verification_reasons,
            "major_point_evidence": major_point_evidence,
            "context_enrichment": context_enrichment,
            "semantic_contract": semantic_contract,
            "code_review_quality": code_review_quality if isinstance(code_review_quality, dict) else {},
        },
    }
