from __future__ import annotations

import re
import time
from dataclasses import dataclass
from threading import Lock
from typing import Any

from app.core.intent_rules import is_mail_search_query

SCOPE_CURRENT_MAIL = "current_mail"
SCOPE_PREVIOUS_RESULTS = "previous_results"
SCOPE_GLOBAL_SEARCH = "global_search"

_VALID_SCOPES = {SCOPE_CURRENT_MAIL, SCOPE_PREVIOUS_RESULTS, SCOPE_GLOBAL_SEARCH}
_MAX_STATE_ITEMS = 256

_CURRENT_MAIL_PATTERNS = ("현재메일", "지금선택메일", "선택메일")
_PREVIOUS_RESULT_PATTERNS = ("그중", "이중", "방금조회", "방금찾은", "조회된메일", "해당메일", "그메일")
_GLOBAL_SEARCH_PATTERNS = ("전체메일", "전체 메일", "메일함전체", "전체에서", "전사메일")
_HUB_QUERY_PATTERNS = (
    "메일과상관없이",
    "메일상관없이",
    "메일말고",
    "메일무관",
    "일반질문",
    "외부검색",
    "웹검색",
    "인터넷검색",
    "기술문서",
    "블로그검색",
)
_EXPLICIT_GLOBAL_SEARCH_INTENT_PATTERNS = (
    "최근메일",
    "지난메일",
    "메일조회",
    "메일검색",
    "최근순",
    "최신순",
    "조회후",
)
_FOLLOWUP_REFERENCE_PATTERNS = ("이슈", "그거", "이거", "해당", "관련", "알려줘", "설명해줘", "정리해줘")


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


def parse_requested_scope(runtime_options: dict[str, Any] | None) -> str:
    """
    runtime_options에서 요청된 scope를 읽어 유효값으로 정규화한다.

    Args:
        runtime_options: 요청의 런타임 옵션 사전

    Returns:
        유효한 scope면 해당 문자열, 아니면 빈 문자열
    """
    if not isinstance(runtime_options, dict):
        return ""
    normalized = str(runtime_options.get("scope") or "").strip().lower()
    if normalized in _VALID_SCOPES:
        return normalized
    return ""


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
    with _STATE_LOCK:
        _evict_expired_states(now=time.time(), ttl_sec=600)
        if search_result_count <= 0:
            _THREAD_STATE.pop(normalized_thread_id, None)
            return
        _THREAD_STATE[normalized_thread_id] = ThreadFollowupState(
            last_search_result_count=search_result_count,
            updated_at=time.time(),
        )
        _evict_overflow_states(max_items=_MAX_STATE_ITEMS)


def get_recent_search_result_count(thread_id: str, ttl_sec: int = 600) -> int:
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


def resolve_effective_scope(
    user_message: str,
    requested_scope: str,
) -> str:
    """
    사용자 입력/요청 옵션을 바탕으로 최종 scope를 결정한다.

    Args:
        user_message: 사용자 입력
        requested_scope: UI에서 명시 선택한 scope

    Returns:
        결정된 scope 또는 빈 문자열
    """
    normalized_requested_scope = str(requested_scope or "").strip().lower()
    if normalized_requested_scope in _VALID_SCOPES:
        return normalized_requested_scope
    explicit_scope = _detect_explicit_scope(user_message=user_message)
    if explicit_scope:
        return explicit_scope
    return ""


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


def build_scope_clarification(
    user_message: str,
    requested_scope: str,
    thread_id: str,
    selected_mail_available: bool,
) -> dict[str, Any] | None:
    """
    모호 질의에서 scope 확인용 clarification payload를 생성한다.

    Args:
        user_message: 사용자 입력
        requested_scope: UI에서 명시 선택한 scope
        thread_id: 대화 스레드 식별자
        selected_mail_available: 현재 요청에 선택 메일 ID가 포함됐는지 여부

    Returns:
        clarification dict 또는 None
    """
    if selected_mail_available and _is_hybrid_related_search_query(user_message=user_message):
        return _build_scope_clarification_options(
            question="현재 메일 기준으로 찾을지, 전체 메일에서 찾을지 선택해 주세요.",
            original_query=user_message,
            selected_mail_available=selected_mail_available,
        )
    if resolve_effective_scope(user_message=user_message, requested_scope=requested_scope):
        return None
    if not selected_mail_available:
        return None
    if _should_clarify_followup_reference_query(user_message=user_message, thread_id=thread_id):
        return _build_scope_clarification_options(
            question="현재 메일 기준으로 볼지, 직전 조회 결과/전체 메일에서 볼지 선택해 주세요.",
            original_query=user_message,
            selected_mail_available=selected_mail_available,
            include_previous_results=True,
        )
    if not _is_ambiguous_mail_search_query(user_message=user_message):
        return None
    return _build_scope_clarification_options(
        question="검색 범위를 선택해 주세요.",
        original_query=user_message,
        selected_mail_available=selected_mail_available,
    )


def apply_scope_instruction(
    user_message: str,
    resolved_scope: str,
    thread_id: str,
) -> str:
    """
    선택된 scope에 맞는 지시문을 사용자 입력 앞에 주입한다.

    Args:
        user_message: 원본 사용자 입력
        resolved_scope: 결정된 scope
        thread_id: 대화 스레드 식별자

    Returns:
        모델 입력에 사용할 주입된 문자열
    """
    normalized = str(user_message or "").strip()
    if not normalized:
        return normalized
    if resolved_scope == SCOPE_CURRENT_MAIL:
        return "[질의 범위] 현재 선택 메일 1건만 기준으로 처리\n" + normalized
    if resolved_scope == SCOPE_PREVIOUS_RESULTS:
        count = get_recent_search_result_count(thread_id=thread_id, ttl_sec=600)
        return f"[질의 범위] 직전 조회 결과 {count}건 안에서만 처리\n{normalized}"
    if resolved_scope == SCOPE_GLOBAL_SEARCH:
        return "[질의 범위] 전체 메일함 기준으로 처리\n" + normalized
    return normalized


def _detect_explicit_scope(user_message: str) -> str:
    """
    사용자 입력에서 명시적으로 드러난 범위 표현을 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        감지된 scope 또는 빈 문자열
    """
    normalized = _normalize_text(user_message=user_message)
    if _is_explicit_hub_query(normalized=normalized):
        return SCOPE_GLOBAL_SEARCH
    if any(token in normalized for token in _CURRENT_MAIL_PATTERNS):
        return SCOPE_CURRENT_MAIL
    if any(token in normalized for token in _PREVIOUS_RESULT_PATTERNS):
        return SCOPE_PREVIOUS_RESULTS
    if any(token in normalized for token in _GLOBAL_SEARCH_PATTERNS):
        return SCOPE_GLOBAL_SEARCH
    return ""


def _is_explicit_hub_query(normalized: str) -> bool:
    """
    메일 문맥 비사용 의도를 명시한 질의인지 판별한다.

    Args:
        normalized: 공백 축약/소문자 정규화 문자열

    Returns:
        메일 무관 질의로 판별되면 True
    """
    text = str(normalized or "").strip()
    if not text:
        return False
    compact = text.replace(" ", "")
    if "현재메일" in compact and not any(token in compact for token in ("말고", "무관", "상관없이")):
        return False
    if is_mail_search_query(text=text):
        return False
    return any(token in text for token in _HUB_QUERY_PATTERNS)


def _is_ambiguous_mail_search_query(user_message: str) -> bool:
    """
    명시 scope 없이 메일 검색 성격이 강한 질의인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        scope 확인이 필요한 모호 메일 검색 질의면 True
    """
    normalized = _normalize_text(user_message=user_message)
    if not normalized:
        return False
    if any(token in normalized for token in _EXPLICIT_GLOBAL_SEARCH_INTENT_PATTERNS):
        return False
    return is_mail_search_query(text=normalized)


def _should_clarify_followup_reference_query(user_message: str, thread_id: str) -> bool:
    """
    직전 조회 맥락에서 모호한 지시어 질의인지 판단한다.

    Args:
        user_message: 사용자 입력
        thread_id: 대화 스레드 식별자

    Returns:
        모호 후속 질의면 True
    """
    recent_count = get_recent_search_result_count(thread_id=thread_id, ttl_sec=600)
    if recent_count <= 0:
        return False
    normalized = _normalize_text(user_message=user_message)
    if not normalized:
        return False
    if is_mail_search_query(text=normalized):
        return False
    return any(token in normalized for token in _FOLLOWUP_REFERENCE_PATTERNS)


def _is_hybrid_related_search_query(user_message: str) -> bool:
    """
    현재메일+유사검색 혼합 질의처럼 scope 충돌 가능성이 높은 문장을 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        하이브리드 scope 질의면 True
    """
    normalized = _normalize_text(user_message=user_message)
    if not normalized:
        return False
    has_current_mail = any(token in normalized for token in _CURRENT_MAIL_PATTERNS)
    if not has_current_mail:
        return False
    has_related = any(token in normalized for token in ("유사", "관련", "비슷", "연관", "같은이슈", "동일이슈"))
    has_search_intent = any(token in normalized for token in ("조회", "검색", "찾아", "찾기"))
    return has_related and has_search_intent


def _build_scope_clarification_options(
    question: str,
    original_query: str,
    selected_mail_available: bool,
    include_previous_results: bool = False,
) -> dict[str, Any] | None:
    """
    scope 선택용 clarification payload를 생성한다.

    Args:
        question: 사용자에게 표시할 질문 문구
        original_query: 원본 질의 문자열
        selected_mail_available: 현재 선택 메일 ID 포함 여부
        include_previous_results: 직전 조회 결과 범위 옵션 포함 여부

    Returns:
        clarification payload 또는 None
    """
    options: list[dict[str, str]] = []
    if selected_mail_available:
        options.append(
            {
                "scope": SCOPE_CURRENT_MAIL,
                "label": "현재 선택 메일",
                "description": "지금 선택한 메일 1건만 기준으로 처리",
            }
        )
    if include_previous_results:
        options.append(
            {
                "scope": SCOPE_PREVIOUS_RESULTS,
                "label": "직전 조회 결과",
                "description": "직전 메일 조회 결과 범위에서만 처리",
            }
        )
    options.append(
        {
            "scope": SCOPE_GLOBAL_SEARCH,
            "label": "전체 사서함",
            "description": "선택 메일과 무관하게 전체 메일에서 검색",
        }
    )
    if len(options) <= 1:
        return None
    return {
        "required": True,
        "question": str(question or "").strip() or "검색 범위를 선택해 주세요.",
        "original_query": str(original_query or "").strip(),
        "options": options,
        "ui_hint": "composer_inline_scope_card",
    }


def _normalize_text(user_message: str) -> str:
    """
    질의 판별용 문자열 정규화를 수행한다.

    Args:
        user_message: 사용자 입력

    Returns:
        공백 축약/소문자 변환 문자열
    """
    compact = re.sub(r"\s+", "", str(user_message or "").strip().lower())
    return compact


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
