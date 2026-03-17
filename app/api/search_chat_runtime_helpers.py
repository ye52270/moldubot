from __future__ import annotations

import json
import time
from typing import Any, Callable

from app.agents.prompts import get_agent_system_prompt
from app.agents.tools import run_mail_post_action
from app.agents.intent_schema import ExecutionStep, IntentDecomposition
from app.api.answer_format_metadata import build_answer_format_metadata
from app.api.search_chat_flow_helpers import (
    build_enrichment_payloads,
    decide_postprocess_execution_policy,
    enrich_major_point_related_mails,
    resolve_web_sources_for_answer,
)
from app.api.search_chat_metadata import (
    build_major_point_evidence,
    extract_aggregated_summary_from_tool_payload,
    extract_evidence_from_tool_payload,
    extract_tool_action,
)
from app.api.search_chat_next_actions_runtime import should_suppress_internal_mail_evidence
from app.core.llm_runtime import invoke_text_messages, resolve_env_model
from app.core.logging_config import get_logger
from app.core.intent_rules import resolve_chat_mode
from app.services.answer_postprocessor import postprocess_final_answer
from app.services.answer_postprocessor_summary import is_current_mail_summary_request
from app.services.visible_answer_service import iter_answer_stream_chunks, sanitize_visible_answer_text
from app.services.next_action_recommender import recommend_next_actions

logger = get_logger(__name__)


def emit_answer_tokens(answer: str, token_callback: Callable[[str], None] | None) -> None:
    """
    최종 답변을 청크로 분해해 토큰 콜백으로 전송한다.

    Args:
        answer: 사용자 노출 최종 답변
        token_callback: 스트림 토큰 콜백
    """
    if not callable(token_callback):
        return
    for chunk in iter_answer_stream_chunks(text=answer):
        normalized = str(chunk or "")
        if not normalized:
            continue
        token_callback(normalized)


def prune_cached_current_mail_step(
    decomposition: IntentDecomposition | None,
    has_cached_context: bool,
    log_prefix: str,
) -> IntentDecomposition | None:
    """
    현재메일 컨텍스트 캐시 히트 시 read_current_mail step을 제거한다.

    Args:
        decomposition: 의도 구조분해 결과
        has_cached_context: 현재메일 컨텍스트 캐시 히트 여부
        log_prefix: 로그 prefix

    Returns:
        step 보정 결과
    """
    if decomposition is None or not has_cached_context:
        return decomposition
    if ExecutionStep.READ_CURRENT_MAIL not in decomposition.steps:
        return decomposition
    filtered_steps = [step for step in decomposition.steps if step != ExecutionStep.READ_CURRENT_MAIL]
    if filtered_steps == list(decomposition.steps):
        return decomposition
    logger.info(
        "%s current_mail cache-hit step pruning: removed=read_current_mail before=%s after=%s",
        log_prefix,
        [step.value for step in decomposition.steps],
        [step.value for step in filtered_steps],
    )
    return decomposition.model_copy(update={"steps": filtered_steps})


def should_use_current_mail_summary_fast_lane(
    decomposition: IntentDecomposition | None,
    user_message: str,
    resolved_scope: str,
    selected_message_id: str,
    has_cached_context: bool,
) -> bool:
    """
    현재메일 요약 fast-lane 적용 가능 여부를 반환한다.

    Args:
        decomposition: 의도 구조분해 결과
        user_message: 사용자 질의
        resolved_scope: 해석된 범위
        selected_message_id: 선택 메일 ID
        has_cached_context: 현재메일 컨텍스트 캐시 히트 여부

    Returns:
        fast-lane 적용 가능하면 True
    """
    if decomposition is None:
        return False
    if str(resolved_scope or "").strip().lower() != "current_mail":
        return False
    if not str(selected_message_id or "").strip():
        return False
    if not has_cached_context:
        return False
    if not is_current_mail_summary_request(user_message=user_message):
        return False
    return ExecutionStep.SUMMARIZE_MAIL in decomposition.steps


def build_current_mail_summary_fastpath_decomposition(
    user_message: str,
    is_current_mail_mode: bool,
    selected_message_id: str,
    summary_decomposition_factory: Callable[[str], IntentDecomposition],
) -> IntentDecomposition | None:
    """
    현재메일 요약 질의는 intent LLM 호출 없이 정책 기반 decomposition을 생성한다.

    Args:
        user_message: 사용자 입력 원문
        is_current_mail_mode: 현재메일 모드 여부
        selected_message_id: 선택 메일 ID
        summary_decomposition_factory: 요약 decomposition 생성기

    Returns:
        fast-path 대상이면 IntentDecomposition, 아니면 None
    """
    if not is_current_mail_mode:
        return None
    if not str(selected_message_id or "").strip():
        return None
    if not is_current_mail_summary_request(user_message=user_message):
        return None
    return summary_decomposition_factory(str(user_message or "").strip())


def invoke_current_mail_summary_fast_lane(
    user_message: str,
    prompt_variant: str,
    summary_line_target: int,
    default_fast_lane_model: str,
    allowed_action_ids: tuple[str, ...],
    invoke_text_messages_fn: Callable[..., str] = invoke_text_messages,
    run_mail_post_action_fn: Callable[..., Any] = run_mail_post_action,
) -> tuple[str, dict[str, Any], float]:
    """
    현재메일 요약 요청을 단일 LLM 호출 fast-lane으로 처리한다.

    Args:
        user_message: 범위 지시가 반영된 사용자 메시지
        prompt_variant: 시스템 프롬프트 variant
        summary_line_target: 요약 줄 수 목표
        default_fast_lane_model: 기본 모델명
        allowed_action_ids: 허용 suggested action ID 목록

    Returns:
        (응답 텍스트, tool_payload, llm 호출 elapsed_ms)
    """
    tool_invoker = run_mail_post_action_fn
    if not callable(tool_invoker) and callable(getattr(run_mail_post_action_fn, "func", None)):
        tool_invoker = getattr(run_mail_post_action_fn, "func")
    tool_payload = tool_invoker(action="current_mail", summary_line_target=summary_line_target)
    if not isinstance(tool_payload, dict):
        tool_payload = {}
    system_prompt = get_agent_system_prompt(prompt_variant)
    model_name = resolve_env_model(
        primary_env="MOLDUBOT_AGENT_MODEL",
        fallback_envs=("DEFAULT_CHAT_MODEL",),
        default_model=default_fast_lane_model,
    )
    response_contract = (
        "{"
        '"format_type":"standard_summary",'
        '"title":"",'
        '"one_line_summary":"",'
        '"summary_lines":["..."],'
        '"major_points":["..."],'
        '"required_actions":["..."],'
        '"suggested_action_ids":["create_todo"]'
        "}"
    )
    user_prompt = (
        "아래는 현재메일 컨텍스트 도구 결과입니다. 이 사실만 근거로 최종 JSON 객체를 생성하세요.\n"
        "반드시 JSON 객체 1개만 출력하고 코드펜스/설명/머리말을 금지합니다.\n"
        f"허용 suggested_action_ids: {', '.join(allowed_action_ids)}\n"
        f"응답 스키마 예시: {response_contract}\n"
        f"[tool_result]\n{json.dumps(tool_payload, ensure_ascii=False)}\n\n"
        f"[user]\n{user_message.strip()}"
    )
    llm_started_at = time.perf_counter()
    response_text = invoke_text_messages_fn(
        model_name=model_name,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        timeout_sec=60,
        temperature=0.0,
    )
    elapsed_ms = (time.perf_counter() - llm_started_at) * 1000
    return response_text, tool_payload, elapsed_ms


def build_selected_mail_evidence_snippet(selected_mail: Any) -> str:
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


def finalize_response_enrichment(
    *,
    log_prefix: str,
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
    intent_decomposition: IntentDecomposition | None,
    resolved_scope: str,
    next_action_id: str,
    evidence_mails: list[dict[str, str]],
    stage_timings: dict[str, float],
    postprocess_started_at: float,
    code_review_quality: dict[str, Any],
    precomputed_next_actions: list[dict[str, str]] | None,
    mail_search_service: Any,
    recommend_next_actions_fn: Callable[..., list[dict[str, str]]] = recommend_next_actions,
    resolve_web_sources_for_answer_fn: Callable[..., tuple[list[dict[str, str]], list[str]]] = resolve_web_sources_for_answer,
    enrich_major_point_related_mails_fn: Callable[..., list[dict[str, Any]]] = enrich_major_point_related_mails,
    build_enrichment_payloads_fn: Callable[..., tuple[Any, Any, Any, dict[str, Any], dict[str, Any]]] = build_enrichment_payloads,
    build_answer_format_metadata_fn: Callable[..., dict[str, Any]] = build_answer_format_metadata,
) -> dict[str, Any]:
    """
    최종 응답 후처리 확장(후속 액션/웹출처/근거/계약 렌더)을 일괄 수행한다.

    Args:
        log_prefix: 로그 prefix
        user_message: 사용자 입력
        answer: 현재 답변 텍스트
        tool_payload: 도구 payload
        intent_decomposition: intent 구조분해 결과
        resolved_scope: 해석 범위
        next_action_id: 강제 next action id
        evidence_mails: 내부 근거 메일 목록
        stage_timings: 단계별 시간 기록 dict
        postprocess_started_at: postprocess 시작 시각(perf_counter)
        code_review_quality: 코드리뷰 품질 메타
        precomputed_next_actions: 모델 계약 기반 후속 액션 목록
        mail_search_service: 연관 메일 탐색 서비스

    Returns:
        메타데이터 병합용 dict
    """
    suppress_internal_evidence = should_suppress_internal_mail_evidence(next_action_id=next_action_id)
    mutable_evidence_mails = [] if suppress_internal_evidence else list(evidence_mails)

    intent_output_format = intent_decomposition.output_format.value if intent_decomposition is not None else ""
    tool_action = extract_tool_action(tool_payload=tool_payload)
    postprocess_policy = decide_postprocess_execution_policy(
        intent_output_format=intent_output_format,
        tool_action=tool_action,
        resolved_scope=resolved_scope,
    )
    logger.info(
        "%s postprocess policy: output_format=%s tool_action=%s skip_web=%s skip_related_mail=%s",
        log_prefix,
        intent_output_format,
        tool_action,
        postprocess_policy.skip_web_sources,
        postprocess_policy.skip_related_mail_enrichment,
    )

    next_actions = precomputed_next_actions or []
    if not next_actions:
        next_actions = recommend_next_actions_fn(
            user_message=user_message,
            answer=answer,
            tool_payload=tool_payload,
            intent_task_type=intent_decomposition.task_type.value if intent_decomposition is not None else "",
            intent_output_format=intent_output_format,
            selector_mode_override="score",
            allow_embeddings=False,
        )

    web_sources_started_at = time.perf_counter()
    web_sources: list[dict[str, str]] = []
    web_verification_reasons: list[str] = []
    if not postprocess_policy.skip_web_sources:
        web_sources, web_verification_reasons = resolve_web_sources_for_answer_fn(
            user_message=user_message,
            intent_task_type=intent_decomposition.task_type.value if intent_decomposition is not None else "",
            resolved_scope=resolved_scope,
            tool_payload=tool_payload,
            intent_confidence=intent_decomposition.confidence if intent_decomposition is not None else None,
            model_answer=answer,
            next_action_id=next_action_id,
        )
    stage_timings["web_sources_ms"] = round((time.perf_counter() - web_sources_started_at) * 1000, 1)

    if isinstance(code_review_quality, dict) and code_review_quality.get("enabled"):
        code_review_quality["web_source_count"] = len(web_sources)
        code_review_quality["has_sources"] = bool(web_sources)

    answer_format = build_answer_format_metadata_fn(
        user_message=user_message,
        answer=answer,
        status="completed",
        decomposition=intent_decomposition,
    )
    major_point_evidence = build_major_point_evidence(
        answer_format=answer_format,
        tool_payload=tool_payload,
        evidence_mails=mutable_evidence_mails,
    )
    related_mail_started_at = time.perf_counter()
    if not suppress_internal_evidence and not postprocess_policy.skip_related_mail_enrichment:
        major_point_evidence = enrich_major_point_related_mails_fn(
            rows=major_point_evidence,
            tool_payload=tool_payload,
            mail_search_service=mail_search_service,
        )
    stage_timings["related_mail_ms"] = round((time.perf_counter() - related_mail_started_at) * 1000, 1)

    contract_render_started_at = time.perf_counter()
    _, _, _, context_enrichment, semantic_contract = build_enrichment_payloads_fn(
        answer=answer,
        answer_format=answer_format,
        tool_payload=tool_payload,
        evidence_mails=mutable_evidence_mails,
        next_actions=next_actions,
        intent_confidence=float(intent_decomposition.confidence if intent_decomposition is not None else 0.0),
        web_sources=web_sources,
    )
    stage_timings["contract_render_ms"] = round((time.perf_counter() - contract_render_started_at) * 1000, 1)
    stage_timings["postprocess"] = round((time.perf_counter() - postprocess_started_at) * 1000, 1)

    logger.info(
        "%s stage_elapsed_ms: intent_parse=%.1f context_fetch=%.1f llm_call_1=%.1f llm_call_2=%.1f "
        "postprocess=%.1f web_sources_ms=%.1f related_mail_ms=%.1f contract_render_ms=%.1f",
        log_prefix,
        float(stage_timings.get("intent_parse", 0.0)),
        float(stage_timings.get("context_fetch", 0.0)),
        float(stage_timings.get("llm_call_1", 0.0)),
        float(stage_timings.get("llm_call_2", 0.0)),
        float(stage_timings.get("postprocess", 0.0)),
        float(stage_timings.get("web_sources_ms", 0.0)),
        float(stage_timings.get("related_mail_ms", 0.0)),
        float(stage_timings.get("contract_render_ms", 0.0)),
    )
    return {
        "evidence_mails": mutable_evidence_mails,
        "next_actions": next_actions,
        "web_sources": web_sources,
        "web_verification_reasons": web_verification_reasons,
        "answer_format": answer_format,
        "major_point_evidence": major_point_evidence,
        "context_enrichment": context_enrichment,
        "semantic_contract": semantic_contract,
        "stage_timings": stage_timings,
        "code_review_quality": code_review_quality,
    }


def render_fast_lane_answer(
    *,
    user_message: str,
    raw_model_content: str,
    tool_payload: dict[str, Any],
) -> str:
    """
    fast-lane 원문을 공통 후처리 후 사용자 노출 텍스트로 정규화한다.

    Args:
        user_message: 사용자 입력
        raw_model_content: fast-lane 모델 원문
        tool_payload: fast-lane tool payload

    Returns:
        사용자 노출 답변
    """
    answer = postprocess_final_answer(
        user_message=user_message,
        answer=raw_model_content,
        tool_payload=tool_payload,
        raw_model_content=raw_model_content,
        chat_mode=resolve_chat_mode(user_message=user_message),
    )
    return sanitize_visible_answer_text(str(answer or "").strip() or raw_model_content)


def extract_tool_result_metadata(tool_payload: dict[str, Any]) -> tuple[list[dict[str, str]], list[str], int | None]:
    """
    tool payload에서 근거/집계 요약/검색 건수를 추출한다.

    Args:
        tool_payload: 도구 payload

    Returns:
        (evidence_mails, aggregated_summary, search_result_count)
    """
    evidence_mails = extract_evidence_from_tool_payload(tool_payload=tool_payload)
    aggregated_summary = extract_aggregated_summary_from_tool_payload(tool_payload=tool_payload)
    search_result_count: int | None = None
    if extract_tool_action(tool_payload=tool_payload) == "mail_search":
        raw_results = tool_payload.get("results") if isinstance(tool_payload, dict) else None
        if isinstance(raw_results, list):
            search_result_count = len(raw_results)
        else:
            raw_count = tool_payload.get("count") if isinstance(tool_payload, dict) else None
            if isinstance(raw_count, int):
                search_result_count = raw_count
    return evidence_mails, aggregated_summary, search_result_count
