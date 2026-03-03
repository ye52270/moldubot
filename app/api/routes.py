from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from app.agents.deep_chat_agent import get_deep_chat_agent, is_openai_key_configured
from app.api import search_chat_flow
from app.api import search_chat_stream_utils
from app.api.contracts import ChatRequest, MailContextRequest
from app.api.data_access import ADDIN_MANIFEST_PATH, resolve_public_base_url
from app.agents.intent_schema import IntentDecomposition
from app.agents.tools import prime_current_mail
from app.core.logging_config import get_logger
from app.services.mail_context_service import build_mail_context_service
from app.services.answer_postprocessor import postprocess_final_answer

router = APIRouter()
logger = get_logger(__name__)
mail_context_service = build_mail_context_service(db_path=search_chat_flow.MAIL_DB_PATH)


@router.get("/healthz")
def healthz() -> dict[str, str]:
    """헬스체크 상태를 반환한다."""
    return {"status": "ok"}


@router.get("/addin/manifest.xml", include_in_schema=False)
def addin_manifest(request: Request) -> Response:
    """요청 호스트 기준으로 동적 치환된 Add-in manifest를 반환한다."""
    xml = ADDIN_MANIFEST_PATH.read_text(encoding="utf-8")
    base_url = resolve_public_base_url(request)
    xml = xml.replace("https://brendon-unboding-maliciously.ngrok-free.dev", base_url)
    return Response(content=xml, media_type="application/xml")


@router.get("/search/chat/runtime-config")
def search_chat_runtime_config() -> dict[str, int]:
    """채팅 런타임 고정 설정값을 반환한다."""
    return {
        "sticky_current_mail_ttl_ms": 10 * 60 * 1000,
        "sticky_current_mail_max_turns": 4,
        "followup_state_ttl_sec": 600,
    }


@router.post("/search/chat")
def search_chat(payload: ChatRequest) -> dict[str, Any]:
    """채팅 요청을 처리하고 deep agent 응답을 반환한다."""
    return _run_search_chat(payload=payload, log_prefix="search_chat")


def _encode_stream_event(event: str, payload: dict[str, Any]) -> str:
    """SSE 포맷 이벤트 문자열을 생성한다."""
    return search_chat_stream_utils.encode_stream_event(event=event, payload=payload)


def _resolve_thread_id(payload: ChatRequest) -> str:
    """`/search/chat` 요청의 thread_id를 정규화한다."""
    return search_chat_stream_utils.resolve_thread_id(payload=payload)


def _is_non_action_query_for_interrupt_retry(
    decomposition: IntentDecomposition,
    user_message: str,
) -> bool:
    """인터럽트 자동 정리 후 재시도 가능한 비-실행 질의인지 판별한다."""
    return search_chat_flow.is_non_action_query_for_interrupt_retry(
        decomposition=decomposition,
        user_message=user_message,
    )


def _run_search_chat(
    payload: ChatRequest,
    log_prefix: str,
    token_callback: Any | None = None,
) -> dict[str, Any]:
    """`/search/chat`과 `/search/chat/stream` 공통 처리 로직을 실행한다."""
    # 테스트/호환성을 위해 routes 네임스페이스에서 patch된 의존성을 flow에 주입한다.
    search_chat_flow.get_deep_chat_agent = get_deep_chat_agent
    search_chat_flow.is_openai_key_configured = is_openai_key_configured
    search_chat_flow.execute_agent_turn = _execute_agent_turn
    search_chat_flow.postprocess_final_answer = postprocess_final_answer
    return search_chat_flow.run_search_chat(
        payload=payload,
        log_prefix=log_prefix,
        token_callback=token_callback,
    )


def _parse_intent_decomposition_safely(user_message: str) -> IntentDecomposition | None:
    """라우팅 보조용 intent 구조분해를 안전하게 파싱한다."""
    return search_chat_flow.parse_intent_decomposition_safely(user_message=user_message)


def _select_prompt_variant_from_intent(decomposition: IntentDecomposition | None) -> str:
    """intent task 유형 기반으로 에이전트 prompt variant를 선택한다."""
    return search_chat_flow.select_prompt_variant_from_intent(decomposition=decomposition)


def _build_intent_clarification(
    user_message: str,
    thread_id: str,
    decomposition: IntentDecomposition | None,
    runtime_options: dict[str, Any],
) -> dict[str, Any] | None:
    """low-confidence 의도에 대해 확인 질문 메타데이터를 구성한다."""
    return search_chat_flow.build_intent_clarification(
        user_message=user_message,
        thread_id=thread_id,
        decomposition=decomposition,
        runtime_options=runtime_options,
    )


def _is_explicit_todo_registration_query(user_message: str) -> bool:
    """사용자 입력이 ToDo 등록 실행 의도인지 판별한다."""
    return search_chat_flow.is_explicit_todo_registration_query(user_message=user_message)


def _build_hitl_confirm_metadata(interrupts: object, thread_id: str) -> dict[str, Any]:
    """HIL 인터럽트 결과를 UI 확인 카드 메타데이터로 변환한다."""
    return search_chat_flow.build_hitl_confirm_metadata(interrupts=interrupts, thread_id=thread_id)


def _execute_agent_turn(agent: Any, user_message: str, thread_id: str) -> dict[str, Any]:
    """agent 실행 인터페이스 호환 래퍼(`execute_turn` 우선, `respond` fallback)."""
    return search_chat_flow.execute_agent_turn(agent=agent, user_message=user_message, thread_id=thread_id)


@router.post("/search/chat/stream")
def search_chat_stream(payload: ChatRequest) -> StreamingResponse:
    """채팅 요청을 진행상태/토큰/최종 완료 이벤트로 전달한다."""
    return StreamingResponse(
        search_chat_stream_utils.stream_search_chat_events(payload=payload, runner=_run_search_chat),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/mail/context")
def mail_context(payload: MailContextRequest) -> dict[str, Any]:
    """Outlook 선택 메일 컨텍스트를 DB/Graph에서 조회한다."""
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
