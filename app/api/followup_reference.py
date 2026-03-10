from __future__ import annotations

import re
import time
from dataclasses import dataclass
from threading import Lock

SCOPE_CURRENT_MAIL = "current_mail"
_MAX_STATE_ITEMS = 256
_DEFAULT_TTL_SEC = 600
_EMAIL_PATTERN = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
_PROBLEM_HINT_TOKENS = ("문제", "이슈", "차단", "실패", "오류", "안되", "안돼", "불가")
_ADDRESS_HINT_TOKENS = ("메일주소", "이메일주소", "주소", "도메인")
_DEICTIC_TOKENS = ("거기", "그주소", "그 주소", "해당주소", "해당 주소", "거기서", "거기에서")
_DELIVERY_TOKENS = ("보내", "발송", "전송", "수신", "어디로", "어떤주소로", "어떤 주소로")
_RECENT_CONTEXT_DEICTIC_TOKENS = (
    "그거",
    "이거",
    "해당",
    "그 내용",
    "이 내용",
    "그 이슈",
    "이 이슈",
)


@dataclass
class ThreadReferenceState:
    """
    스레드별 후속 지시어 해석에 필요한 최소 상태를 저장한다.

    Attributes:
        problem_email: 직전 확정된 문제 메일 주소
        updated_at: 마지막 갱신 시각(epoch seconds)
    """

    problem_email: str
    updated_at: float


_STATE_LOCK = Lock()
_THREAD_REFERENCES: dict[str, ThreadReferenceState] = {}
_THREAD_RECENT_CONTEXT: dict[str, dict[str, object]] = {}


def remember_followup_reference(
    thread_id: str,
    user_message: str,
    answer: str,
    resolved_scope: str,
    is_current_mail_mode: bool,
) -> None:
    """
    직전 턴에서 확정된 문제 메일주소를 스레드 상태에 저장한다.

    Args:
        thread_id: 대화 스레드 식별자
        user_message: 사용자 입력 원문
        answer: 최종 답변 텍스트
        resolved_scope: 해석된 질의 범위
        is_current_mail_mode: current_mail 모드 여부
    """
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return
    if not _is_current_mail_scope(resolved_scope=resolved_scope, is_current_mail_mode=is_current_mail_mode):
        return
    if not _is_problem_address_question(user_message=user_message):
        return
    emails = _extract_emails(text=answer)
    if not emails:
        return
    problem_email = emails[0]
    with _STATE_LOCK:
        now = time.time()
        _evict_expired_states(now=now, ttl_sec=_DEFAULT_TTL_SEC)
        _THREAD_REFERENCES[normalized_thread_id] = ThreadReferenceState(
            problem_email=problem_email,
            updated_at=now,
        )
        _evict_overflow_states(max_items=_MAX_STATE_ITEMS)


def remember_recent_turn_context(
    thread_id: str,
    resolved_scope: str,
    evidence_mails: list[dict[str, str]] | None,
) -> None:
    """
    후속 질의 안정화를 위해 스레드별 최소 컨텍스트를 저장한다.

    Args:
        thread_id: 대화 스레드 식별자
        resolved_scope: 이번 턴의 최종 scope
        evidence_mails: 이번 턴 근거메일 목록
    """
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return
    evidence_rows = evidence_mails if isinstance(evidence_mails, list) else []
    normalized_evidence: list[dict[str, str]] = []
    for row in evidence_rows[:3]:
        if not isinstance(row, dict):
            continue
        subject = str(row.get("subject") or "").strip()
        snippet = str(row.get("snippet") or "").strip()
        if not subject and not snippet:
            continue
        normalized_evidence.append(
            {
                "subject": subject,
                "snippet": snippet[:140],
            }
        )
    with _STATE_LOCK:
        now = time.time()
        _evict_expired_states(now=now, ttl_sec=_DEFAULT_TTL_SEC)
        _THREAD_RECENT_CONTEXT[normalized_thread_id] = {
            "resolved_scope": str(resolved_scope or "").strip().lower(),
            "evidence_top3": normalized_evidence,
            "updated_at": now,
        }
        _evict_recent_context_overflow(max_items=_MAX_STATE_ITEMS)


def build_recent_context_hint(
    thread_id: str,
    user_message: str,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> str:
    """
    지시어 기반 후속 질문에서 최근 턴의 최소 컨텍스트 힌트를 생성한다.

    Args:
        thread_id: 대화 스레드 식별자
        user_message: 사용자 입력
        ttl_sec: 상태 TTL(초)

    Returns:
        모델 입력 앞에 주입할 문맥 힌트 문자열. 없으면 빈 문자열.
    """
    if not _is_recent_context_deictic_question(user_message=user_message):
        return ""
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return ""
    with _STATE_LOCK:
        now = time.time()
        _evict_expired_states(now=now, ttl_sec=ttl_sec)
        context = _THREAD_RECENT_CONTEXT.get(normalized_thread_id)
    if not isinstance(context, dict):
        return ""
    scope = str(context.get("resolved_scope") or "").strip().lower()
    scope_label = _render_scope_label(scope=scope)
    evidence_top3 = context.get("evidence_top3")
    evidence_rows = evidence_top3 if isinstance(evidence_top3, list) else []
    hint_lines = ["[대화 문맥]", f"- 직전 질의 범위: {scope_label}"]
    for index, row in enumerate(evidence_rows[:2], start=1):
        if not isinstance(row, dict):
            continue
        subject = str(row.get("subject") or "").strip() or "제목 없음"
        snippet = str(row.get("snippet") or "").strip()
        if snippet:
            hint_lines.append(f"- 최근 근거 {index}: {subject} — {snippet}")
        else:
            hint_lines.append(f"- 최근 근거 {index}: {subject}")
    hint_lines.append("- 현재 질문의 지시어는 위 범위/근거를 우선 참조한다.")
    return "\n".join(hint_lines)


def build_followup_reference_hint(
    thread_id: str,
    user_message: str,
    resolved_scope: str,
    is_current_mail_mode: bool,
    ttl_sec: int = _DEFAULT_TTL_SEC,
) -> str:
    """
    지시대명사 후속 질의를 위한 문맥 힌트를 생성한다.

    Args:
        thread_id: 대화 스레드 식별자
        user_message: 사용자 입력 원문
        resolved_scope: 해석된 질의 범위
        is_current_mail_mode: current_mail 모드 여부
        ttl_sec: 상태 TTL(초)

    Returns:
        모델 입력 앞에 주입할 문맥 힌트 문자열. 없으면 빈 문자열.
    """
    if not _is_current_mail_scope(resolved_scope=resolved_scope, is_current_mail_mode=is_current_mail_mode):
        return ""
    if not _is_deictic_delivery_question(user_message=user_message):
        return ""
    state = _get_thread_reference_state(thread_id=thread_id, ttl_sec=ttl_sec)
    if state is None or not state.problem_email:
        return ""
    return (
        "[대화 문맥]\n"
        f"- 직전 확정 문제 메일주소: {state.problem_email}\n"
        "- 현재 질문의 지시어(거기/그 주소)는 위 메일주소를 가리킨다.\n"
        "- 위 주소 기준으로 어떤 대상 주소로 전송되는지 우선 답한다."
    )


def reset_followup_reference_state_for_test() -> None:
    """
    테스트 용도로 후속 참조 상태를 초기화한다.
    """
    with _STATE_LOCK:
        _THREAD_REFERENCES.clear()
        _THREAD_RECENT_CONTEXT.clear()


def _is_current_mail_scope(resolved_scope: str, is_current_mail_mode: bool) -> bool:
    """
    current_mail 맥락에서만 참조 상태를 사용하도록 범위를 검증한다.

    Args:
        resolved_scope: 해석된 질의 범위
        is_current_mail_mode: current_mail 모드 여부

    Returns:
        current_mail 맥락이면 True
    """
    return str(resolved_scope or "").strip().lower() == SCOPE_CURRENT_MAIL and bool(is_current_mail_mode)


def _normalize_compact(text: str) -> str:
    """
    질의 판별을 위해 공백 제거/소문자 정규화를 수행한다.

    Args:
        text: 원본 문자열

    Returns:
        정규화 문자열
    """
    return str(text or "").replace(" ", "").lower()


def _is_problem_address_question(user_message: str) -> bool:
    """
    문제 메일주소 식별 질문인지 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        문제 주소 식별형 질문이면 True
    """
    compact = _normalize_compact(user_message)
    has_problem = any(token in compact for token in _PROBLEM_HINT_TOKENS)
    has_address = any(token in compact for token in _ADDRESS_HINT_TOKENS)
    has_ask = any(token in compact for token in ("어떤", "무슨", "뭐", "알려")) or ("?" in str(user_message or ""))
    return has_problem and has_address and has_ask


def _is_deictic_delivery_question(user_message: str) -> bool:
    """
    지시어 기반 전송 대상 질문인지 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        지시어 + 전송의도 질문이면 True
    """
    compact = _normalize_compact(user_message)
    has_deictic = any(token in compact for token in _DEICTIC_TOKENS)
    has_delivery = any(token in compact for token in _DELIVERY_TOKENS)
    return has_deictic and has_delivery


def _is_recent_context_deictic_question(user_message: str) -> bool:
    """
    최근 턴 컨텍스트 주입이 필요한 지시어 질문인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        지시어 기반 후속 질문이면 True
    """
    compact = _normalize_compact(user_message)
    if not compact:
        return False
    return any(token.replace(" ", "") in compact for token in _RECENT_CONTEXT_DEICTIC_TOKENS)


def _render_scope_label(scope: str) -> str:
    """
    scope 문자열을 사용자 친화 라벨로 변환한다.

    Args:
        scope: scope 문자열

    Returns:
        표시용 scope 라벨
    """
    normalized = str(scope or "").strip().lower()
    if normalized == "current_mail":
        return "현재 선택 메일"
    if normalized == "previous_results":
        return "직전 조회 결과"
    if normalized == "global_search":
        return "전체 사서함"
    return "미지정"


def _extract_emails(text: str) -> list[str]:
    """
    문자열에서 이메일 주소를 순서대로 추출(중복 제거)한다.

    Args:
        text: 검사 대상 문자열

    Returns:
        추출된 이메일 주소 목록
    """
    found = _EMAIL_PATTERN.findall(str(text or ""))
    deduped: list[str] = []
    seen: set[str] = set()
    for item in found:
        normalized = str(item or "").strip().lower()
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(normalized)
    return deduped


def _get_thread_reference_state(thread_id: str, ttl_sec: int) -> ThreadReferenceState | None:
    """
    TTL 범위 내에서 스레드 참조 상태를 조회한다.

    Args:
        thread_id: 대화 스레드 식별자
        ttl_sec: 상태 TTL(초)

    Returns:
        스레드 참조 상태 또는 None
    """
    normalized_thread_id = str(thread_id or "").strip()
    if not normalized_thread_id:
        return None
    with _STATE_LOCK:
        now = time.time()
        _evict_expired_states(now=now, ttl_sec=ttl_sec)
        return _THREAD_REFERENCES.get(normalized_thread_id)


def _evict_expired_states(now: float, ttl_sec: int) -> None:
    """
    TTL이 만료된 스레드 상태를 제거한다.

    Args:
        now: 기준 시각(epoch seconds)
        ttl_sec: 상태 TTL(초)
    """
    expired_keys = [
        thread_id
        for thread_id, state in _THREAD_REFERENCES.items()
        if (now - float(state.updated_at)) > ttl_sec
    ]
    for thread_id in expired_keys:
        _THREAD_REFERENCES.pop(thread_id, None)
    expired_context_keys = [
        thread_id
        for thread_id, state in _THREAD_RECENT_CONTEXT.items()
        if (now - float(state.get("updated_at") or 0.0)) > ttl_sec
    ]
    for thread_id in expired_context_keys:
        _THREAD_RECENT_CONTEXT.pop(thread_id, None)


def _evict_overflow_states(max_items: int) -> None:
    """
    상태 개수가 제한을 초과하면 오래된 순으로 제거한다.

    Args:
        max_items: 최대 허용 상태 수
    """
    overflow = len(_THREAD_REFERENCES) - int(max_items)
    if overflow <= 0:
        return
    sorted_items = sorted(_THREAD_REFERENCES.items(), key=lambda item: float(item[1].updated_at))
    for thread_id, _ in sorted_items[:overflow]:
        _THREAD_REFERENCES.pop(thread_id, None)


def _evict_recent_context_overflow(max_items: int) -> None:
    """
    최근 턴 컨텍스트 저장소 개수가 제한을 초과하면 오래된 순으로 제거한다.

    Args:
        max_items: 최대 허용 상태 수
    """
    overflow = len(_THREAD_RECENT_CONTEXT) - int(max_items)
    if overflow <= 0:
        return
    sorted_items = sorted(
        _THREAD_RECENT_CONTEXT.items(),
        key=lambda item: float(item[1].get("updated_at") or 0.0),
    )
    for thread_id, _ in sorted_items[:overflow]:
        _THREAD_RECENT_CONTEXT.pop(thread_id, None)
