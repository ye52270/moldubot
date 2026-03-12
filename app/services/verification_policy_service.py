from __future__ import annotations

from dataclasses import dataclass, field

WEB_TRIGGER_KEYWORDS: tuple[str, ...] = (
    "인터넷으로검색",
    "인터넷검색",
    "웹검색",
    "외부자료",
    "외부근거",
    "외부출처",
    "공식문서",
    "레퍼런스",
    "출처포함",
    "링크와함께",
)
VERIFICATION_REQUEST_KEYWORDS: tuple[str, ...] = (
    "검증",
    "맞는지",
    "맞아",
    "정확",
    "사실",
    "근거",
    "출처",
    "팩트체크",
    "사실확인",
)
EXPLICIT_EXTERNAL_REQUEST_KEYWORDS: tuple[str, ...] = (
    "외부",
    "웹",
    "web",
    "인터넷",
    "검색",
    "참고",
    "레퍼런스",
    "reference",
    "공식문서",
    "공식 문서",
    "외부자료",
    "출처",
)
BLOCK_EXTERNAL_REQUEST_KEYWORDS: tuple[str, ...] = (
    "외부검색없이",
    "외부검색하지마",
    "내부메일만",
    "메일본문만",
)


@dataclass(slots=True)
class VerificationDecision:
    """
    외부 검증(웹 출처 검색) 정책 판단 결과.

    Attributes:
        enabled: 웹 검증 실행 여부
        reasons: 정책 근거 목록
    """

    enabled: bool
    reasons: list[str] = field(default_factory=list)


def decide_web_verification(
    user_message: str,
    intent_task_type: str,
    resolved_scope: str,
    tool_payload: dict[str, object] | None = None,
    intent_confidence: float | None = None,
    model_answer: str = "",
) -> VerificationDecision:
    """
    웹 검색 기반 사실 검증 수행 여부를 정책적으로 판단한다.

    Args:
        user_message: 사용자 질의
        intent_task_type: 의도 task type
        resolved_scope: 최종 scope
        tool_payload: 최근 도구 payload
        intent_confidence: 의도 confidence
        model_answer: 모델 최종 응답

    Returns:
        검증 정책 판단 결과
    """
    del intent_task_type, intent_confidence, model_answer
    query = _normalize_for_token_policy(user_message=user_message)
    if not query:
        return VerificationDecision(enabled=False, reasons=["empty_query"])

    reasons: list[str] = []
    current_mail_scope = _is_current_mail_scope(resolved_scope=resolved_scope, tool_payload=tool_payload)
    explicit_block = _contains_any_token(query=query, tokens=BLOCK_EXTERNAL_REQUEST_KEYWORDS)
    explicit_external = _contains_any_token(query=query, tokens=EXPLICIT_EXTERNAL_REQUEST_KEYWORDS)
    explicit_verification = _contains_any_token(query=query, tokens=VERIFICATION_REQUEST_KEYWORDS)
    keyword_trigger = _contains_any_token(query=query, tokens=WEB_TRIGGER_KEYWORDS)
    explicit_request = explicit_external or explicit_verification or keyword_trigger

    if explicit_block:
        reasons.append("explicit_internal_only_request")
    if explicit_external:
        reasons.append("explicit_external_request")
    if explicit_verification:
        reasons.append("explicit_verification_request")
    if keyword_trigger:
        reasons.append("keyword_trigger")

    if explicit_block:
        return VerificationDecision(enabled=False, reasons=reasons)

    if current_mail_scope:
        allowed = explicit_request
        if not allowed:
            reasons.append("blocked_by_current_mail_scope")
        return VerificationDecision(enabled=allowed, reasons=reasons)

    enabled = explicit_request
    if not enabled:
        reasons.append("policy_not_matched")
    return VerificationDecision(enabled=enabled, reasons=reasons)


def _is_current_mail_scope(resolved_scope: str, tool_payload: dict[str, object] | None) -> bool:
    """
    요청이 current_mail 문맥인지 판별한다.

    Args:
        resolved_scope: 최종 scope 문자열
        tool_payload: 최근 도구 payload

    Returns:
        current_mail 범위면 True
    """
    normalized_scope = str(resolved_scope or "").strip().lower()
    if normalized_scope == "current_mail":
        return True
    payload = tool_payload if isinstance(tool_payload, dict) else {}
    action = str(payload.get("action") or "").strip().lower()
    return action == "current_mail"


def _contains_any_token(query: str, tokens: tuple[str, ...]) -> bool:
    """
    문자열에 지정 토큰 중 하나라도 포함되는지 확인한다.

    Args:
        query: 검사 대상 문자열
        tokens: 토큰 목록

    Returns:
        포함 시 True
    """
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    return any(token in normalized for token in tokens)


def _normalize_for_token_policy(user_message: str) -> str:
    """
    외부검색 트리거 토큰 정책 판별을 위한 입력 정규화를 수행한다.

    Args:
        user_message: 사용자 발화

    Returns:
        공백/구두점을 제거한 소문자 문자열
    """
    normalized = str(user_message or "").strip().lower()
    if not normalized:
        return ""
    return "".join(ch for ch in normalized if ch.isalnum() or ("가" <= ch <= "힣"))
