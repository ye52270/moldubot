from __future__ import annotations

import json
import threading
from datetime import datetime, timezone
from queue import Empty, Queue
from typing import Any, Callable

from app.api.contracts import ChatRequest

STREAM_PROGRESS_HEARTBEAT_SEC = 1.0


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
        payload={"phase": "received", "message": "요청을 확인했어요."},
    )
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
            yield encode_stream_event(
                event="progress",
                payload={"phase": "processing", "message": "근거 메일과 맥락을 분석 중입니다."},
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
        payload={"phase": "finalizing", "message": "최종 결과를 정리하고 있습니다."},
    )
    yield encode_stream_event(event="completed", payload=response_payload)
