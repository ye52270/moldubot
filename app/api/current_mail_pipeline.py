from __future__ import annotations

import re
import time
from dataclasses import dataclass
from threading import Lock

from app.core.intent_rules import is_mail_search_query, is_mail_summary_skill_query

STICKY_CURRENT_MAIL_TTL_SEC = 600
STICKY_CURRENT_MAIL_MAX_TURNS = 4

_REQUESTED_SCOPE_CURRENT_MAIL = "current_mail"
_REQUESTED_SCOPE_GLOBAL_SEARCH = "global_search"

_EXPLICIT_CURRENT_MAIL_PATTERN = re.compile(r"현재\s*메일")
_EXPLICIT_GLOBAL_PATTERNS = (
    "전체메일",
    "전체 메일",
    "전체사서함",
    "전체 사서함",
    "메일함 전체",
    "메일 조회",
    "메일 검색",
    "관련 메일",
    "최근 메일",
    "지난 메일",
)
_EXPLICIT_HUB_PATTERNS = (
    "메일과 상관없이",
    "메일 상관없이",
    "메일 말고",
    "메일 무관",
    "일반 질문",
    "일반질문",
    "외부 검색",
    "외부검색",
    "웹 검색",
    "웹검색",
    "인터넷 검색",
    "인터넷검색",
    "기술문서",
    "블로그 검색",
)
_MULTI_MAIL_ANALYSIS_PATTERNS = (
    "메일들",
    "여러 메일",
    "복수 메일",
    "메일 전체",
    "전체 메일",
    "관련 메일들",
    "메일 간",
    "비교",
    "패턴",
    "추이",
)
_IMPLICIT_FOLLOWUP_HINTS = (
    "정리",
    "요약",
    "분석",
    "설명",
    "알려",
    "금액",
    "비용",
    "예산",
    "영향",
    "원인",
    "리스크",
    "왜",
    "무엇",
    "어떻게",
)
_IMPLICIT_REFERENCE_TOKENS = (
    "이 ",
    "이메일",
    "이 메일",
    "이견적",
    "이 견적",
    "이프로젝트",
    "이 프로젝트",
    "해당",
    "그 메일",
    "그메일",
    "이 이슈",
    "이이슈",
)
_IMPLICIT_BLOCKING_TOKENS = (
    "조회",
    "검색",
    "찾아",
    "찾기",
    "예약",
    "등록",
    "생성",
    "추가",
    "전체",
)


@dataclass
class StickyCurrentMailState:
    """
    스레드별 현재메일 sticky 상태를 보관한다.

    Attributes:
        remaining_turns: 남은 암시 후속 허용 턴 수
        updated_at: 마지막 갱신 시각(epoch seconds)
    """

    remaining_turns: int
    updated_at: float


_STATE_LOCK = Lock()
_STICKY_STATE: dict[str, StickyCurrentMailState] = {}


def is_current_mail_query(text: str) -> bool:
    """
    현재 메일 컨텍스트가 필요한 질의인지 판별한다.

    Args:
        text: 사용자 입력 원문

    Returns:
        `현재메일` 표현이 포함되면 True
    """
    normalized = str(text or "").strip()
    if not normalized:
        return False
    compact = normalized.lower().replace(" ", "")
    if "현재메일" in compact:
        return True
    return bool(_EXPLICIT_CURRENT_MAIL_PATTERN.search(normalized))


def resolve_current_mail_mode(
    user_message: str,
    thread_id: str,
    selected_mail_available: bool,
    requested_scope: str,
) -> bool:
    """
    현재 요청을 current_mail 모드로 처리할지 판별한다.

    Args:
        user_message: 사용자 입력
        thread_id: 대화 스레드 식별자
        selected_mail_available: 선택 메일 ID 포함 여부
        requested_scope: runtime_options.scope 값

    Returns:
        current_mail 모드 여부
    """
    normalized_scope = str(requested_scope or "").strip().lower()
    if normalized_scope == _REQUESTED_SCOPE_CURRENT_MAIL:
        return True
    if normalized_scope == _REQUESTED_SCOPE_GLOBAL_SEARCH:
        return False
    if _is_explicit_hub_query(user_message=user_message):
        return False
    if _is_multi_mail_analysis_query(user_message=user_message):
        return False
    if selected_mail_available and is_mail_summary_skill_query(user_message=user_message):
        return True
    if is_current_mail_query(text=user_message):
        return True
    if _is_explicit_global_mail_query(user_message=user_message):
        return False
    if not selected_mail_available:
        return False
    if _is_implicit_followup_query(user_message=user_message):
        return True
    return _consume_sticky_followup_turn(thread_id=thread_id)


def remember_sticky_current_mail(
    thread_id: str,
    user_message: str,
    requested_scope: str,
    selected_mail_available: bool,
    is_current_mail_mode: bool,
) -> None:
    """
    요청 처리 후 current_mail sticky 상태를 갱신한다.

    Args:
        thread_id: 대화 스레드 식별자
        user_message: 사용자 입력
        requested_scope: runtime_options.scope 값
        selected_mail_available: 선택 메일 ID 포함 여부
        is_current_mail_mode: 이번 요청의 current_mail 판별 결과
    """
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return
    normalized_scope = str(requested_scope or "").strip().lower()
    if (
        normalized_scope == _REQUESTED_SCOPE_GLOBAL_SEARCH
        or _is_explicit_global_mail_query(user_message=user_message)
        or _is_explicit_hub_query(user_message=user_message)
    ):
        _clear_sticky_state(thread_id=normalized_thread_id)
        return
    should_refresh = (
        selected_mail_available
        and (
            normalized_scope == _REQUESTED_SCOPE_CURRENT_MAIL
            or is_current_mail_query(text=user_message)
            or bool(is_current_mail_mode)
        )
    )
    if not should_refresh:
        return
    with _STATE_LOCK:
        _evict_expired_states(now=time.time(), ttl_sec=STICKY_CURRENT_MAIL_TTL_SEC)
        _STICKY_STATE[normalized_thread_id] = StickyCurrentMailState(
            remaining_turns=STICKY_CURRENT_MAIL_MAX_TURNS,
            updated_at=time.time(),
        )


def reset_sticky_current_mail_state_for_test() -> None:
    """
    테스트를 위해 sticky current-mail 상태를 초기화한다.
    """
    with _STATE_LOCK:
        _STICKY_STATE.clear()


def _is_explicit_global_mail_query(user_message: str) -> bool:
    """
    사용자 입력이 전체 메일 조회 명시 질의인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        전체 메일 조회를 명시하면 True
    """
    normalized = str(user_message or "").strip().lower()
    if not normalized:
        return False
    return any(token in normalized for token in _EXPLICIT_GLOBAL_PATTERNS)


def _is_explicit_hub_query(user_message: str) -> bool:
    """
    메일 무관 일반 질의로 명시된 입력인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        메일 문맥 비사용 의도가 명시되면 True
    """
    normalized = str(user_message or "").strip().lower()
    if not normalized:
        return False
    compact = normalized.replace(" ", "")
    if "현재메일" in compact and not any(token in compact for token in ("말고", "무관", "상관없이")):
        return False
    if is_mail_search_query(text=normalized):
        return False
    return any(token in normalized for token in _EXPLICIT_HUB_PATTERNS)


def _is_multi_mail_analysis_query(user_message: str) -> bool:
    """
    다건 메일 기반 분석/비교 성격 질의인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        여러 메일을 전제로 한 질의면 True
    """
    normalized = str(user_message or "").strip().lower()
    if not normalized:
        return False
    return any(token in normalized for token in _MULTI_MAIL_ANALYSIS_PATTERNS)


def _is_implicit_followup_query(user_message: str) -> bool:
    """
    현재메일 문맥의 암시적 후속 질의 가능성을 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        암시적 후속 질의로 볼 수 있으면 True
    """
    normalized = str(user_message or "").strip().lower()
    if not normalized:
        return False
    if any(token in normalized for token in _IMPLICIT_BLOCKING_TOKENS):
        return False
    has_followup_hint = any(token in normalized for token in _IMPLICIT_FOLLOWUP_HINTS)
    if not has_followup_hint:
        return False
    return any(token in normalized for token in _IMPLICIT_REFERENCE_TOKENS)


def _consume_sticky_followup_turn(thread_id: str) -> bool:
    """
    스레드의 sticky 상태를 1턴 소모하고 사용 가능 여부를 반환한다.

    Args:
        thread_id: 대화 스레드 식별자

    Returns:
        사용 가능하면 True, 아니면 False
    """
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return False
    with _STATE_LOCK:
        now = time.time()
        _evict_expired_states(now=now, ttl_sec=STICKY_CURRENT_MAIL_TTL_SEC)
        state = _STICKY_STATE.get(normalized_thread_id)
        if state is None or state.remaining_turns <= 0:
            _STICKY_STATE.pop(normalized_thread_id, None)
            return False
        state.remaining_turns -= 1
        state.updated_at = now
        if state.remaining_turns <= 0:
            _STICKY_STATE.pop(normalized_thread_id, None)
        else:
            _STICKY_STATE[normalized_thread_id] = state
        return True


def _clear_sticky_state(thread_id: str) -> None:
    """
    특정 스레드의 sticky current-mail 상태를 제거한다.

    Args:
        thread_id: 대화 스레드 식별자
    """
    with _STATE_LOCK:
        _STICKY_STATE.pop(str(thread_id or "").strip(), None)


def _evict_expired_states(now: float, ttl_sec: int) -> None:
    """
    만료된 sticky 상태를 제거한다.

    Args:
        now: 현재 시각(epoch seconds)
        ttl_sec: 상태 TTL(초)
    """
    expired_keys = [
        key
        for key, state in _STICKY_STATE.items()
        if now - state.updated_at > ttl_sec
    ]
    for key in expired_keys:
        _STICKY_STATE.pop(key, None)
