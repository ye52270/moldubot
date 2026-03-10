from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any, Callable

from app.api.contracts import ChatRequest
from app.core.intent_rules import is_code_review_query

STREAM_PROGRESS_HEARTBEAT_SEC = 1.0
GENERAL_STREAM_PHASE_STEPS: tuple[tuple[str, str], ...] = (
    ("received", "요청을 확인했어요."),
    ("retrieving_context", "메일 컨텍스트를 불러오는 중입니다."),
    ("analyzing", "요청을 처리하고 있어요."),
    ("critic_review", "응답 품질을 점검하고 있어요."),
    ("revising", "응답을 다듬고 있어요."),
    ("finalizing", "최종 결과를 정리하고 있습니다."),
)

CODE_REVIEW_STREAM_PHASE_STEPS: tuple[tuple[str, str], ...] = (
    ("received", "요청을 확인했어요."),
    ("retrieving_context", "메일 컨텍스트를 불러오는 중입니다."),
    ("analyzing", "코드/문맥을 분석하고 있어요."),
    ("critic_review", "품질 점검(critic)을 수행 중입니다."),
    ("revising", "리뷰 결과를 보정하고 있어요."),
    ("finalizing", "최종 결과를 정리하고 있습니다."),
)


def encode_stream_event(event: str, payload: dict[str, Any]) -> str:
    """SSE 포맷 이벤트 문자열을 생성한다."""
    body = json.dumps(payload, ensure_ascii=False)
    return f"event: {event}\ndata: {body}\n\n"


def resolve_thread_id(payload: ChatRequest) -> str:
    """`/search/chat` 요청의 thread_id를 정규화한다."""
    normalized = str(payload.thread_id or "").strip()
    if normalized:
        return normalized
    return f"outlook_{int(datetime.now(tz=timezone.utc).timestamp())}"


def stream_search_chat_events(
    payload: ChatRequest,
    runner: Callable[[ChatRequest, str, Callable[[str], None] | None], dict[str, Any]],
) -> Any:
    """SSE 이벤트 스트림 제너레이터를 생성한다."""
    result_queue: Queue[dict[str, Any]] = Queue(maxsize=1)
    token_queue: Queue[str] = Queue()
    phase_steps = _resolve_phase_steps(payload=payload)
    def _run_turn_worker() -> None:
        response_payload = runner(
            payload,
            "search_chat_stream",
            lambda token: token_queue.put(str(token or "")),
        )
        result_queue.put(response_payload)

    worker = threading.Thread(target=_run_turn_worker, daemon=True)
    worker.start()

    yield encode_stream_event(
        event="progress",
        payload={"phase": "received", "message": "요청을 확인했어요.", "step": 1, "total_steps": len(phase_steps)},
    )
    heartbeat_count = 0
    while worker.is_alive() or not token_queue.empty():
        emitted_token = False
        while not token_queue.empty():
            token_text = str(token_queue.get_nowait() or "")
            if not token_text.strip():
                continue
            emitted_token = True
            yield encode_stream_event(
                event="token",
                payload={"phase": "token", "text": token_text},
            )
        if not emitted_token:
            heartbeat_count += 1
            progress_phase, progress_message, progress_step = _resolve_progress_state(
                heartbeat_count=heartbeat_count,
                phase_steps=phase_steps,
            )
            yield encode_stream_event(
                event="progress",
                payload={
                    "phase": progress_phase,
                    "message": progress_message,
                    "step": progress_step,
                    "total_steps": len(phase_steps),
                },
            )
        worker.join(timeout=STREAM_PROGRESS_HEARTBEAT_SEC)

    try:
        response_payload = result_queue.get_nowait()
    except Empty:
        response_payload = {
            "status": "failed",
            "thread_id": resolve_thread_id(payload=payload),
            "answer": "내부 오류로 응답을 생성하지 못했습니다.",
            "source": "internal-error",
            "metadata": {"elapsed_ms": 0.0},
        }

    yield encode_stream_event(
        event="progress",
        payload={
            "phase": "finalizing",
            "message": "최종 결과를 정리하고 있습니다.",
            "step": len(phase_steps),
            "total_steps": len(phase_steps),
        },
    )
    yield encode_stream_event(event="completed", payload=response_payload)


def _resolve_phase_steps(payload: ChatRequest) -> tuple[tuple[str, str], ...]:
    """
    질의 성격에 따라 progress 단계 문구 세트를 선택한다.

    Args:
        payload: `/search/chat` 요청 본문

    Returns:
        진행 단계 튜플 목록
    """
    if is_code_review_query(user_message=str(payload.message or "")):
        return CODE_REVIEW_STREAM_PHASE_STEPS
    return GENERAL_STREAM_PHASE_STEPS


def _resolve_progress_state(
    heartbeat_count: int,
    phase_steps: tuple[tuple[str, str], ...],
) -> tuple[str, str, int]:
    """
    heartbeat 횟수에 따라 진행 단계 문구를 순환 선택한다.

    Args:
        heartbeat_count: heartbeat 누적 횟수(1-base)
        phase_steps: 선택된 진행 단계/문구 목록

    Returns:
        (phase, message, step) 튜플
    """
    normalized = max(1, int(heartbeat_count))
    if not phase_steps:
        return "processing", "요청을 처리하고 있어요.", 1
    max_pre_final_index = max(0, len(phase_steps) - 2)
    index = min(normalized, max_pre_final_index)
    phase, message = phase_steps[index]
    return phase, message, index + 1
