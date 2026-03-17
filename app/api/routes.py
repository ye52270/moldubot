from __future__ import annotations

import sqlite3
from typing import Any

from fastapi import APIRouter, Request
from fastapi.responses import Response, StreamingResponse

from app.agents.deep_chat_agent import get_deep_chat_agent, is_openai_key_configured
from app.agents.tools import clear_current_mail
from app.api import search_chat_flow
from app.api import search_chat_stream_utils
from app.api.contracts import ChatRequest, MailContextRequest
from app.api.data_access import ADDIN_MANIFEST_PATH, resolve_public_base_url
from app.agents.tools import prime_current_mail
from app.core.logging_config import get_logger
from app.services.mail_context_service import build_mail_context_service
from app.services.mail_text_utils import extract_recipients_from_body, extract_sender_display_name
from app.services.answer_postprocessor import postprocess_final_answer

router = APIRouter()
logger = get_logger(__name__)
mail_context_service = build_mail_context_service(db_path=search_chat_flow.MAIL_DB_PATH)
_FLOW_EXECUTE_AGENT_TURN = search_chat_flow.execute_agent_turn


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


@router.post("/search/chat")
def search_chat(payload: ChatRequest) -> dict[str, Any]:
    """채팅 요청을 처리하고 deep agent 응답을 반환한다."""
    return _run_search_chat(payload=payload, log_prefix="search_chat")


def _encode_stream_event(event: str, payload: dict[str, Any]) -> str:
    """SSE 포맷 이벤트 문자열을 생성한다."""
    return search_chat_stream_utils.encode_stream_event(event=event, payload=payload)


def _run_search_chat(
    payload: ChatRequest,
    log_prefix: str,
    token_callback: Any | None = None,
) -> dict[str, Any]:
    """`/search/chat`과 `/search/chat/stream` 공통 처리 로직을 실행한다."""
    # 테스트/호환성을 위해 routes 네임스페이스에서 patch된 의존성을 flow에 주입한다.
    search_chat_flow.get_deep_chat_agent = get_deep_chat_agent
    search_chat_flow.is_openai_key_configured = is_openai_key_configured
    search_chat_flow.mail_context_service = mail_context_service
    search_chat_flow.clear_current_mail = clear_current_mail
    search_chat_flow.execute_agent_turn = _execute_agent_turn
    search_chat_flow.postprocess_final_answer = postprocess_final_answer
    return search_chat_flow.run_search_chat(
        payload=payload,
        log_prefix=log_prefix,
        token_callback=token_callback,
    )


def _resolve_mail_importance_label(message_id: str) -> str:
    """
    선택 메일의 중요도(category)를 DB에서 조회해 UI 표시용 라벨로 반환한다.

    Args:
        message_id: 조회 대상 message_id

    Returns:
        중요도 라벨(예: `긴급`, `회신필요`) 또는 빈 문자열
    """
    normalized_message_id = str(message_id or "").strip()
    if not normalized_message_id:
        return ""
    db_path = search_chat_flow.MAIL_DB_PATH
    if not db_path.exists():
        return ""
    conn = sqlite3.connect(str(db_path))
    try:
        has_category = any(
            str(row[1]).lower() == "category"
            for row in conn.execute("PRAGMA table_info(emails)").fetchall()
        )
        if not has_category:
            return ""
        row = conn.execute(
            "SELECT COALESCE(category, '') AS category_text FROM emails WHERE message_id = ? LIMIT 1",
            (normalized_message_id,),
        ).fetchone()
        return str(row[0] if row else "").strip()
    except sqlite3.Error as exc:
        logger.warning("mail_context.importance_lookup_failed: message_id=%s error=%s", normalized_message_id, exc)
        return ""
    finally:
        conn.close()


def _execute_agent_turn(agent: Any, user_message: str, thread_id: str) -> dict[str, Any]:
    """agent 실행 인터페이스 호환 래퍼(`execute_turn` 우선, `respond` fallback)."""
    return _FLOW_EXECUTE_AGENT_TURN(agent=agent, user_message=user_message, thread_id=thread_id)


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
        importance_label = _resolve_mail_importance_label(message_id=result.mail.message_id)
        return {
            "status": result.status,
            "source": result.source,
            "mail": {
                "message_id": result.mail.message_id,
                "subject": result.mail.subject,
                "from_address": result.mail.from_address,
                "from_display_name": extract_sender_display_name(result.mail.from_address),
                "to_recipients": extract_recipients_from_body(result.mail.body_text),
                "received_date": result.mail.received_date,
                "body_text": result.mail.body_text,
                "web_link": result.mail.web_link,
                "importance": importance_label,
                "category": importance_label,
            },
        }
    return {
        "status": result.status,
        "source": result.source,
        "reason": result.reason,
    }
