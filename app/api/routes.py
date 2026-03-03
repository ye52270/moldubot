from __future__ import annotations

import json
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse
from openai import OpenAIError

from app.agents.deep_chat_agent import FALLBACK_EMPTY_RESPONSE, get_deep_chat_agent, is_openai_key_configured
from app.agents.tools import clear_current_mail, prime_current_mail
from app.api.contracts import (
    ChatRequest,
    MailContextRequest,
)
from app.api.current_mail_pipeline import (
    is_current_mail_query,
)
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
from app.api.answer_format_metadata import build_answer_format_metadata
from app.api.data_access import (
    ADDIN_MANIFEST_PATH,
    resolve_public_base_url,
)
from app.core.logging_config import get_logger
from app.core.metrics import get_chat_metrics_tracker
from app.services.answer_postprocessor import postprocess_final_answer
from app.services.mail_context_service import build_mail_context_service

router = APIRouter()
logger = get_logger(__name__)
chat_metrics = get_chat_metrics_tracker()
ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"
mail_context_service = build_mail_context_service(db_path=MAIL_DB_PATH)
@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/addin/manifest.xml", include_in_schema=False)
def addin_manifest(request: Request) -> Response:
    xml = ADDIN_MANIFEST_PATH.read_text(encoding="utf-8")
    base_url = resolve_public_base_url(request)
    # Existing manifest uses a fixed ngrok URL. Replace it on-the-fly for current host.
    xml = xml.replace("https://brendon-unboding-maliciously.ngrok-free.dev", base_url)
    return Response(content=xml, media_type="application/xml")


@router.get("/search/chat/runtime-config")
def search_chat_runtime_config() -> dict[str, int]:
    return {
        "sticky_current_mail_ttl_ms": 10 * 60 * 1000,
        "sticky_current_mail_max_turns": 4,
        "followup_state_ttl_sec": 600,
    }


@router.post("/search/chat")
def search_chat(payload: ChatRequest) -> dict[str, Any]:
    """
    채팅 요청을 처리하고 deep agent 응답을 반환한다.

    Args:
        payload: 채팅 요청 본문

    Returns:
        상태/스레드/응답/메타데이터를 포함한 표준 응답 객체
    """
    return _run_search_chat(payload=payload, log_prefix="search_chat")


def _encode_stream_event(event: str, payload: dict[str, Any]) -> str:
    """
    SSE 포맷 이벤트 문자열을 생성한다.

    Args:
        event: SSE 이벤트 타입
        payload: JSON 직렬화 가능한 페이로드

    Returns:
        `text/event-stream` 포맷 문자열
    """
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n"


def _resolve_thread_id(payload: ChatRequest) -> str:
    """
    `/search/chat` 요청의 thread_id를 정규화한다.

    Args:
        payload: 채팅 요청 본문

    Returns:
        비어 있지 않은 스레드 식별자
    """
    normalized = str(payload.thread_id or "").strip()
    if normalized:
        return normalized
    return f"outlook_{int(datetime.now(tz=timezone.utc).timestamp())}"


def _run_search_chat(payload: ChatRequest, log_prefix: str) -> dict[str, Any]:
    """
    `/search/chat`과 `/search/chat/stream` 공통 처리 로직을 실행한다.

    Args:
        payload: 채팅 요청 본문
        log_prefix: 로깅 접두어

    Returns:
        표준 응답 페이로드
    """
    started_at = time.perf_counter()
    text = str(payload.message or "").strip()
    thread_id = _resolve_thread_id(payload=payload)
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

    resolved_scope = resolve_effective_scope(user_message=text, requested_scope=requested_scope)
    evidence_mails: list[dict[str, str]] = []
    aggregated_summary: list[str] = []
    search_result_count: int | None = None
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
            agent = get_deep_chat_agent()
            scoped_message = apply_scope_instruction(
                user_message=text,
                resolved_scope=resolved_scope,
                thread_id=thread_id,
            )
            turn_result = _execute_agent_turn(agent=agent, user_message=scoped_message, thread_id=thread_id)
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
                        "confirm": _build_hitl_confirm_metadata(
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
        },
    }


def _build_hitl_confirm_metadata(interrupts: object, thread_id: str) -> dict[str, Any]:
    """
    HIL 인터럽트 결과를 UI 확인 카드 메타데이터로 변환한다.

    Args:
        interrupts: 에이전트 인터럽트 목록
        thread_id: 대화 스레드 ID

    Returns:
        확인 카드 렌더링용 메타데이터
    """
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


def _execute_agent_turn(agent: Any, user_message: str, thread_id: str) -> dict[str, Any]:
    """
    agent 실행 인터페이스 호환 래퍼(`execute_turn` 우선, `respond` fallback).

    Args:
        agent: deep agent 인스턴스
        user_message: 사용자 메시지
        thread_id: 스레드 식별자

    Returns:
        표준화된 턴 실행 결과
    """
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


@router.post("/search/chat/stream")
def search_chat_stream(payload: ChatRequest) -> StreamingResponse:
    """
    채팅 요청을 단일 완료 이벤트(SSE)로 전달한다.

    Args:
        payload: 채팅 요청 본문

    Returns:
        진행상태와 최종 응답을 포함한 SSE 응답
    """

    def event_generator() -> Any:
        response_payload = _run_search_chat(payload=payload, log_prefix="search_chat_stream")
        yield _encode_stream_event(event="completed", payload=response_payload)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/mail/context")
def mail_context(payload: MailContextRequest) -> dict[str, Any]:
    """
    Outlook 선택 메일 컨텍스트를 DB/Graph에서 조회한다.

    Args:
        payload: 선택 메일 조회 요청 본문

    Returns:
        조회 상태/소스/메일 컨텍스트 응답
    """
    result = mail_context_service.get_mail_context(
        message_id=payload.message_id,
        mailbox_user=payload.mailbox_user,
    )
    if result.mail is not None:
        prime_current_mail(mail=result.mail)
        return {
            "status": result.status,
            "source": result.source,
            "mail": {
                "message_id": result.mail.message_id,
                "subject": result.mail.subject,
                "from_address": result.mail.from_address,
                "received_date": result.mail.received_date,
                "body_text": result.mail.body_text,
                "web_link": result.mail.web_link,
            },
        }
    return {
        "status": result.status,
        "source": result.source,
        "reason": result.reason,
    }
