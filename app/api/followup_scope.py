from __future__ import annotations

import time
from dataclasses import dataclass
from threading import Lock

SCOPE_CURRENT_MAIL = "current_mail"
SCOPE_PREVIOUS_RESULTS = "previous_results"
SCOPE_GLOBAL_SEARCH = "global_search"

_MAX_STATE_ITEMS = 256
_DEFAULT_TTL_SEC = 600


@dataclass
class ThreadFollowupState:
    """
    스레드별 후속 질의 판단에 필요한 최소 상태를 보관한다.

    Attributes:
        last_search_result_count: 직전 검색 결과 건수
        updated_at: 마지막 상태 갱신 시각(epoch seconds)
    """

    last_search_result_count: int
    updated_at: float


_STATE_LOCK = Lock()
_THREAD_STATE: dict[str, ThreadFollowupState] = {}


def remember_followup_search_result(
    thread_id: str,
    search_result_count: int | None,
) -> None:
    """
    스레드별 직전 검색 건수를 저장한다.

    Args:
        thread_id: 대화 스레드 식별자
        search_result_count: 이번 질의의 검색 결과 건수
    """
    if search_result_count is None:
        return
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return
    now = time.time()
    with _STATE_LOCK:
        _evict_expired_states(now=now, ttl_sec=_DEFAULT_TTL_SEC)
        if search_result_count <= 0:
            _THREAD_STATE.pop(normalized_thread_id, None)
            return
        _THREAD_STATE[normalized_thread_id] = ThreadFollowupState(
            last_search_result_count=search_result_count,
            updated_at=now,
        )
        _evict_overflow_states(max_items=_MAX_STATE_ITEMS)


def get_recent_search_result_count(thread_id: str, ttl_sec: int = _DEFAULT_TTL_SEC) -> int:
    """
    스레드의 최근 검색 결과 건수를 TTL 범위 내에서 조회한다.

    Args:
        thread_id: 대화 스레드 식별자
        ttl_sec: 상태 유효 시간(초)

    Returns:
        최근 검색 결과 건수. 없거나 만료면 0
    """
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return 0
    with _STATE_LOCK:
        now = time.time()
        _evict_expired_states(now=now, ttl_sec=ttl_sec)
        state = _THREAD_STATE.get(normalized_thread_id)
        if state is None:
            return 0
        return max(int(state.last_search_result_count), 0)


def resolve_default_scope(is_current_mail_mode: bool) -> str:
    """
    명시 scope가 없을 때 기본 scope를 결정한다.

    Args:
        is_current_mail_mode: 현재메일 질의 판별 결과

    Returns:
        기본 scope(`current_mail` 또는 `global_search`)
    """
    if bool(is_current_mail_mode):
        return SCOPE_CURRENT_MAIL
    return SCOPE_GLOBAL_SEARCH


def _evict_expired_states(now: float, ttl_sec: int) -> None:
    """
    만료된 스레드 상태를 메모리에서 제거한다.

    Args:
        now: 현재 시각(epoch seconds)
        ttl_sec: 상태 유효 시간(초)
    """
    expired_keys = [
        key
        for key, state in _THREAD_STATE.items()
        if now - state.updated_at > ttl_sec
    ]
    for key in expired_keys:
        _THREAD_STATE.pop(key, None)


def _evict_overflow_states(max_items: int) -> None:
    """
    저장된 상태가 최대 개수를 초과하면 오래된 항목부터 제거한다.

    Args:
        max_items: 최대 상태 개수
    """
    if len(_THREAD_STATE) <= max_items:
        return
    sorted_keys = sorted(_THREAD_STATE, key=lambda key: _THREAD_STATE[key].updated_at)
    overflow_count = len(_THREAD_STATE) - max_items
    for key in sorted_keys[:overflow_count]:
        _THREAD_STATE.pop(key, None)


def reset_followup_scope_state_for_test() -> None:
    """
    테스트를 위해 follow-up 상태 저장소를 초기화한다.
    """
    with _STATE_LOCK:
        _THREAD_STATE.clear()
