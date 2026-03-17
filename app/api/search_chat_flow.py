from __future__ import annotations
import time
from pathlib import Path
from typing import Any, Callable
from app.agents.deep_chat_agent import FALLBACK_EMPTY_RESPONSE, get_deep_chat_agent, is_openai_key_configured
from app.agents.intent_parser import get_intent_parser
from app.agents.tools import clear_current_mail, prime_current_mail, run_mail_post_action
from app.agents.tools import reset_search_scope_contract, set_search_scope_contract
from app.api.answer_format_metadata import build_answer_format_metadata
from app.api.contracts import ChatRequest
from app.api.current_mail_pipeline import (
    remember_sticky_current_mail,
    resolve_current_mail_mode,
)
from app.api.search_chat_flow_helpers import (
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
    parse_intent_decomposition_safely,
    select_prompt_variant_from_intent,
)
from app.api.search_chat_response_builders import (
    build_pending_approval_response,
    build_web_search_direct_response,
)
from app.api.search_chat_context_helpers import (
    build_intent_clarification_payload_if_needed,
    build_summary_policy_decomposition,
    hydrate_selected_mail_context,
)
from app.api.followup_scope import resolve_default_scope
from app.api.search_chat_metadata import (
    build_evidence_mail_item,
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
)
from app.api.search_chat_stream_utils import resolve_thread_id
from app.api.search_chat_runtime_helpers import (
    build_current_mail_summary_fastpath_decomposition,
    build_selected_mail_evidence_snippet,
    emit_answer_tokens,
    extract_tool_result_metadata,
    finalize_response_enrichment,
    invoke_current_mail_summary_fast_lane,
    prune_cached_current_mail_step,
    render_fast_lane_answer,
    should_use_current_mail_summary_fast_lane,
)
from app.api.search_chat_response_helpers import (
    build_completed_response_payload,
    build_web_direct_response_with_metadata,
)
from app.core.logging_config import get_logger
from app.core.intent_rules import is_mail_summary_skill_query
from app.core.llm_runtime import invoke_text_messages
from app.core.metrics import get_chat_metrics_tracker
from app.services.code_review_quality_service import refine_code_review_answer_with_metadata
from app.services.mail_context_service import build_mail_context_service
from app.services.mail_search_service import MailSearchService
from app.services.next_action_contract_extractor import resolve_next_actions_from_model_content
from app.services.next_action_recommender import recommend_next_actions
from app.services.visible_answer_service import sanitize_visible_answer_text
from app.services.web_source_search_service import search_web_sources
logger = get_logger(__name__)
chat_metrics = get_chat_metrics_tracker()
ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"
mail_context_service = build_mail_context_service(db_path=MAIL_DB_PATH)
mail_search_service = MailSearchService(db_path=MAIL_DB_PATH)
DEFAULT_FAST_LANE_MODEL = "gpt-4o-mini"
FAST_LANE_SUGGESTED_ACTION_IDS = ("draft_reply", "analyze_code_snippet", "create_todo", "create_calendar_event", "book_meeting_room", "web_search", "search_related_mails")


def _should_auto_retry_after_interrupt(
    user_message: str,
    intent_decomposition: Any,
    turn_result: dict[str, Any],
) -> bool:
    """
    비-실행 질의에서 남아있는 승인 인터럽트를 자동 정리 후 재시도할지 판단한다.

    Args:
        user_message: 사용자 질의
        intent_decomposition: 의도 구조분해 결과
        turn_result: 1차 agent 실행 결과

    Returns:
        자동 재시도 대상이면 True
    """
    _ = user_message
    interrupts = turn_result.get("interrupts")
    if not isinstance(interrupts, list) or not interrupts:
        return False
    if intent_decomposition is None:
        return True
    if str(getattr(intent_decomposition, "task_type", "")).endswith("action"):
        return False
    action_steps = {"book_meeting_room", "book_calendar_event"}
    step_values = {str(getattr(step, "value", step)) for step in getattr(intent_decomposition, "steps", [])}
    if step_values & action_steps:
        return False
    return True


def _dismiss_pending_interrupts(agent: Any, turn_result: dict[str, Any]) -> None:
    """
    인터럽트가 남아있을 때 거절 응답으로 정리해 다음 턴 재시도를 가능하게 만든다.

    Args:
        agent: deep agent 인스턴스
        turn_result: 인터럽트 결과 payload
    """
    if not hasattr(agent, "resume_pending_actions"):
        return
    interrupts = turn_result.get("interrupts")
    if not isinstance(interrupts, list):
        return
    for item in interrupts:
        if not isinstance(item, dict):
            continue
        interrupt_id = str(item.get("interrupt_id") or "").strip()
        if not interrupt_id:
            continue
        try:
            agent.resume_pending_actions(confirm_token=interrupt_id, approved=False, thread_id=None)
        except TypeError:
            agent.resume_pending_actions(confirm_token=interrupt_id, approved=False)
        except Exception as exc:
            logger.info("search_chat_stream pending interrupt dismiss skipped: interrupt_id=%s error=%s", interrupt_id, exc)


def run_search_chat(
    payload: ChatRequest,
    log_prefix: str,
    token_callback: Callable[[str], None] | None = None,
) -> dict[str, Any]:
    """`/search/chat`과 `/search/chat/stream` 공통 처리 로직을 실행한다."""
    started_at = time.perf_counter()
    stage_timings: dict[str, float] = {"intent_parse": 0.0, "context_fetch": 0.0, "llm_call_1": 0.0, "llm_call_2": 0.0, "postprocess": 0.0, "web_sources_ms": 0.0, "related_mail_ms": 0.0, "contract_render_ms": 0.0}
    text = str(payload.message or "").strip()
    ui_render_mode = "card" if is_mail_summary_skill_query(user_message=text) else "plain_lists"
    thread_id = resolve_thread_id(payload=payload)
    preview = (text[:80] + "...") if len(text) > 80 else text
    logger.info("%s 요청 수신: length=%s preview=%s thread_id=%s", log_prefix, len(text), preview, thread_id)
    selected_email_id = str(payload.email_id or "").strip()
    is_current_mail_mode = resolve_current_mail_mode(
        user_message=text,
        thread_id=thread_id,
        selected_mail_available=bool(selected_email_id),
        requested_scope="",
    )
    remember_sticky_current_mail(
        thread_id=thread_id,
        user_message=text,
        requested_scope="",
        selected_mail_available=bool(selected_email_id),
        is_current_mail_mode=is_current_mail_mode,
    )
    logger.info("%s 선택 메일 식별자 수신: email_id=%s message_id=%s mailbox_user=%s", log_prefix, selected_email_id, selected_email_id, str(payload.mailbox_user or "").strip())
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
    intent_decomposition = build_current_mail_summary_fastpath_decomposition(
        user_message=text,
        is_current_mail_mode=is_current_mail_mode,
        selected_message_id=selected_message_id,
        summary_decomposition_factory=build_summary_policy_decomposition,
    )
    if intent_decomposition is None:
        intent_decomposition = parse_intent_decomposition_safely(
            user_message=text,
            parser_factory=get_intent_parser,
            has_selected_mail=bool(selected_email_id),
            selected_message_id_exists=bool(selected_message_id),
        )
    else:
        logger.info(
            "%s intent fast-path 적용: task_type=%s steps=%s",
            log_prefix,
            intent_decomposition.task_type.value,
            [step.value for step in intent_decomposition.steps],
        )
    stage_timings["intent_parse"] = round((time.perf_counter() - started_at) * 1000, 1)
    preliminary_scope = resolve_default_scope(is_current_mail_mode=is_current_mail_mode)
    intent_clarification = build_intent_clarification(
        user_message=text,
        thread_id=thread_id,
        decomposition=intent_decomposition,
        runtime_options=runtime_options,
        is_current_mail_mode=is_current_mail_mode,
        selected_mail_available=bool(selected_message_id),
    )
    clarification_payload = build_intent_clarification_payload_if_needed(
        intent_clarification=intent_clarification,
        log_prefix=log_prefix,
        thread_id=thread_id,
        intent_decomposition=intent_decomposition,
        is_current_mail_mode=is_current_mail_mode,
        preliminary_scope=preliminary_scope,
        selected_message_id=selected_message_id,
        scope_metadata_builder=build_scope_metadata,
        build_answer_format_metadata_fn=build_answer_format_metadata,
        ui_render_mode=ui_render_mode,
    )
    if clarification_payload is not None:
        return clarification_payload
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
    context_state = hydrate_selected_mail_context(
        selected_message_id=selected_message_id,
        is_current_mail_mode=is_current_mail_mode,
        payload_mailbox_user=str(payload.mailbox_user or "").strip(),
        preloaded_mail_context=preloaded_mail_context,
        mail_context_getter=mail_context_service.get_mail_context,
        clear_current_mail_fn=clear_current_mail,
        prime_current_mail_fn=prime_current_mail,
        build_evidence_mail_item_fn=build_evidence_mail_item,
        evidence_snippet_builder=build_selected_mail_evidence_snippet,
        prune_cached_step_fn=prune_cached_current_mail_step,
        intent_decomposition=intent_decomposition,
        log_prefix=log_prefix,
    )
    did_clear_current_mail = bool(context_state.get("did_clear_current_mail"))
    selected_mail = context_state.get("selected_mail")
    has_cached_current_mail_context = bool(context_state.get("has_cached_current_mail_context"))
    intent_decomposition = context_state.get("intent_decomposition")
    loaded_evidence = context_state.get("evidence_mails")
    if isinstance(loaded_evidence, list):
        evidence_mails = loaded_evidence
    stage_timings["context_fetch"] = round((time.perf_counter() - started_at) * 1000, 1)
    if next_action_id == ACTION_ID_WEB_SEARCH:
        mail_subject = str(getattr(selected_mail, "subject", "") or "").strip()
        mail_summary = str(getattr(selected_mail, "summary_text", "") or "").strip()
        return build_web_direct_response_with_metadata(
            builder_fn=build_web_search_direct_response,
            user_message=text,
            thread_id=thread_id,
            is_current_mail_mode=is_current_mail_mode,
            resolved_scope=resolved_scope,
            selected_message_id=selected_message_id,
            did_clear_current_mail=did_clear_current_mail,
            clear_current_mail_fn=clear_current_mail,
            build_answer_format_metadata_fn=build_answer_format_metadata,
            selected_mail_subject=mail_subject,
            selected_mail_summary=mail_summary,
            search_web_sources_fn=search_web_sources,
            scope_metadata=scope_metadata,
            elapsed_ms=(time.perf_counter() - started_at) * 1000,
            intent_task_type=intent_decomposition.task_type.value if intent_decomposition is not None else "",
            intent_output_format=intent_decomposition.output_format.value if intent_decomposition is not None else "",
            intent_confidence=float(intent_decomposition.confidence if intent_decomposition is not None else 0.0),
            ui_render_mode=ui_render_mode,
        )
    answer = ""
    raw_answer = ""
    raw_model_output = ""
    raw_model_content = ""
    tool_payload = {}
    precomputed_next_actions: list[dict[str, str]] | None = None
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
        llm_call_1_ms = 0.0
        llm_call_2_ms = 0.0
        scope_token: object | None = None
        try:
            scope_token = set_search_scope_contract(scope_contract)
            prompt_variant = select_prompt_variant_from_intent(
                decomposition=intent_decomposition,
                user_message=text,
                resolved_scope=resolved_scope,
            )
            agent_thread_id = thread_id
            scoped_message = str(text or "").strip()
            if str(resolved_scope or "").strip().lower() == "current_mail":
                scoped_message = f"[질의 범위] 현재 선택 메일\n{scoped_message}".strip()
            use_current_mail_fast_lane = should_use_current_mail_summary_fast_lane(
                decomposition=intent_decomposition,
                user_message=text,
                resolved_scope=resolved_scope,
                selected_message_id=selected_message_id,
                has_cached_context=has_cached_current_mail_context,
            )
            fast_lane_completed = False
            if use_current_mail_fast_lane:
                logger.info("%s current_mail_summary fast_lane 적용: cache_hit=true", log_prefix)
                try:
                    fast_answer, fast_tool_payload, llm_elapsed_ms = invoke_current_mail_summary_fast_lane(
                        user_message=scoped_message,
                        prompt_variant=prompt_variant,
                        summary_line_target=(
                            intent_decomposition.summary_line_target if intent_decomposition is not None else 5
                        ),
                        default_fast_lane_model=DEFAULT_FAST_LANE_MODEL,
                        allowed_action_ids=FAST_LANE_SUGGESTED_ACTION_IDS,
                        invoke_text_messages_fn=invoke_text_messages,
                        run_mail_post_action_fn=run_mail_post_action,
                    )
                    llm_call_2_ms = llm_elapsed_ms
                    raw_model_content = str(fast_answer or "").strip() or FALLBACK_EMPTY_RESPONSE
                    raw_model_output = raw_model_content
                    raw_answer = raw_model_content
                    answer = render_fast_lane_answer(
                        user_message=text,
                        raw_model_content=raw_model_content,
                        tool_payload=fast_tool_payload if isinstance(fast_tool_payload, dict) else {},
                    )
                    tool_payload = fast_tool_payload if isinstance(fast_tool_payload, dict) else {}
                    precomputed_next_actions = resolve_next_actions_from_model_content(
                        raw_model_content=raw_model_content,
                        tool_payload=tool_payload,
                    )
                    emit_answer_tokens(answer=answer, token_callback=token_callback)
                    stage_timings["llm_call_1"] = round(llm_call_1_ms, 1)
                    stage_timings["llm_call_2"] = round(llm_call_2_ms, 1)
                    logger.info("%s 처리 완료: source=%s answer_length=%s", log_prefix, source, len(answer))
                    fast_lane_completed = True
                except Exception as fast_lane_error:
                    logger.warning(
                        "%s current_mail_summary fast_lane 실패: deep-agent 경로로 폴백 (%s)",
                        log_prefix,
                        fast_lane_error,
                    )
            if not fast_lane_completed:
                agent = get_deep_chat_agent(prompt_variant=prompt_variant)
                llm_call_1_started_at = time.perf_counter()
                turn_result = execute_agent_turn(
                    agent=agent,
                    user_message=scoped_message,
                    thread_id=agent_thread_id,
                )
                llm_call_1_ms = (time.perf_counter() - llm_call_1_started_at) * 1000
                turn_status = str(turn_result.get("status") or "").strip()
                if turn_status == "interrupted" and _should_auto_retry_after_interrupt(
                    user_message=text,
                    intent_decomposition=intent_decomposition,
                    turn_result=turn_result,
                ):
                    _dismiss_pending_interrupts(agent=agent, turn_result=turn_result)
                    retry_started_at = time.perf_counter()
                    turn_result = execute_agent_turn(
                        agent=agent,
                        user_message=scoped_message,
                        thread_id=agent_thread_id,
                    )
                    llm_call_2_ms = (time.perf_counter() - retry_started_at) * 1000
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
                            prompt_variant=prompt_variant,
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
                        metadata["ui_render_mode"] = ui_render_mode
                    emit_answer_tokens(answer=answer, token_callback=token_callback)
                    return response_payload
                answer = str(turn_result.get("answer") or "").strip() or FALLBACK_EMPTY_RESPONSE
                raw_answer = answer
                raw_model_output = read_agent_raw_model_output(agent=agent) or answer
                raw_model_content = read_agent_raw_model_content(agent=agent) or raw_model_output
                tool_payload = read_agent_tool_payload(agent=agent)
                answer = read_agent_final_answer(agent=agent) or answer
                stage_timings["llm_call_1"] = round(llm_call_1_ms, 1)
                stage_timings["llm_call_2"] = round(llm_call_2_ms, 1)
                if not answer:
                    answer = FALLBACK_EMPTY_RESPONSE
                answer = sanitize_visible_answer_text(answer)
                precomputed_next_actions = resolve_next_actions_from_model_content(
                    raw_model_content=raw_model_content,
                    tool_payload=tool_payload,
                )
                emit_answer_tokens(answer=answer, token_callback=token_callback)
                tool_action = extract_tool_action(tool_payload=tool_payload)
                tool_evidence, tool_aggregated_summary, tool_search_result_count = extract_tool_result_metadata(
                    tool_payload=tool_payload
                )
                if tool_action == "mail_search":
                    evidence_mails = tool_evidence
                    search_result_count = tool_search_result_count
                elif tool_evidence:
                    evidence_mails = tool_evidence
                if tool_aggregated_summary:
                    aggregated_summary = tool_aggregated_summary
                answer, code_review_quality = refine_code_review_answer_with_metadata(
                    user_message=text,
                    answer=answer,
                    tool_payload=tool_payload,
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

    # NOTE: elapsed_ms는 메인 응답 생성 구간만 포함하며, 아래 후속 enrichment/추천 계산 시간은 제외한다.
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

    postprocess_started_at = time.perf_counter()
    enrichment = finalize_response_enrichment(
        log_prefix=log_prefix,
        user_message=text,
        answer=answer,
        tool_payload=tool_payload,
        intent_decomposition=intent_decomposition,
        resolved_scope=resolved_scope,
        next_action_id=next_action_id,
        evidence_mails=evidence_mails,
        stage_timings=stage_timings,
        postprocess_started_at=postprocess_started_at,
        code_review_quality=code_review_quality if isinstance(code_review_quality, dict) else {},
        precomputed_next_actions=precomputed_next_actions,
        mail_search_service=mail_search_service,
        recommend_next_actions_fn=recommend_next_actions,
        resolve_web_sources_for_answer_fn=resolve_web_sources_for_answer,
        enrich_major_point_related_mails_fn=enrich_major_point_related_mails,
        build_enrichment_payloads_fn=build_enrichment_payloads,
        build_answer_format_metadata_fn=build_answer_format_metadata,
    )
    evidence_mails = enrichment["evidence_mails"]
    next_actions = enrichment["next_actions"]
    web_sources = enrichment["web_sources"]
    web_verification_reasons = enrichment["web_verification_reasons"]
    answer_format = enrichment["answer_format"]
    major_point_evidence = enrichment["major_point_evidence"]
    context_enrichment = enrichment["context_enrichment"]
    semantic_contract = enrichment["semantic_contract"]
    stage_timings = enrichment["stage_timings"]
    code_review_quality = enrichment["code_review_quality"]

    return build_completed_response_payload(
        thread_id=thread_id,
        answer=answer,
        agent_thread_id=str(agent_thread_id or thread_id),
        source=source,
        raw_answer=raw_answer,
        raw_model_output=raw_model_output,
        raw_model_content=raw_model_content,
        is_current_mail_mode=is_current_mail_mode,
        evidence_mails=evidence_mails,
        aggregated_summary=aggregated_summary,
        search_result_count=search_result_count,
        resolved_scope=resolved_scope,
        scope_metadata=scope_metadata,
        elapsed_ms=elapsed_ms,
        answer_format=answer_format,
        intent_task_type=intent_decomposition.task_type.value if intent_decomposition is not None else "",
        intent_output_format=intent_decomposition.output_format.value if intent_decomposition is not None else "",
        intent_confidence=float(intent_decomposition.confidence if intent_decomposition is not None else 0.0),
        next_actions=next_actions,
        web_sources=web_sources,
        web_verification_reasons=web_verification_reasons,
        major_point_evidence=major_point_evidence,
        context_enrichment=context_enrichment,
        semantic_contract=semantic_contract,
        stage_timings=stage_timings,
        code_review_quality=code_review_quality if isinstance(code_review_quality, dict) else {},
        ui_render_mode=ui_render_mode,
        tool_payload=tool_payload,
    )
