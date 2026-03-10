from __future__ import annotations

from dataclasses import dataclass, field

WEB_TRIGGER_KEYWORDS: tuple[str, ...] = (
    "트렌드",
    "trend",
    "최신",
    "뉴스",
    "검색",
    "찾아",
    "이슈",
    "문제",
    "오류",
    "장애",
    "원인",
    "해결",
    "기술",
    "보안",
    "ssl",
    "api",
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
    "최신",
    "뉴스",
    "트렌드",
    "기술검토",
    "기술 검토",
    "레퍼런스",
    "reference",
    "공식문서",
    "공식 문서",
)
UNCERTAINTY_TOKENS: tuple[str, ...] = ("추정", "가능성", "확인 필요", "불확실", "단정하기 어렵")
LOW_CONFIDENCE_THRESHOLD = 0.72


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
    query = str(user_message or "").strip().lower()
    if not query:
        return VerificationDecision(enabled=False, reasons=["empty_query"])

    reasons: list[str] = []
    current_mail_scope = _is_current_mail_scope(resolved_scope=resolved_scope, tool_payload=tool_payload)
    explicit_external = _contains_any_token(query=query, tokens=EXPLICIT_EXTERNAL_REQUEST_KEYWORDS)
    explicit_verification = _contains_any_token(query=query, tokens=VERIFICATION_REQUEST_KEYWORDS)
    low_confidence_target = _is_low_confidence_target(
        intent_task_type=intent_task_type,
        intent_confidence=intent_confidence,
        model_answer=model_answer,
    )
    keyword_trigger = _contains_any_token(query=query, tokens=WEB_TRIGGER_KEYWORDS)

    if explicit_external:
        reasons.append("explicit_external_request")
    if explicit_verification:
        reasons.append("explicit_verification_request")
    if low_confidence_target:
        reasons.append("low_confidence_or_uncertain_answer")
    if keyword_trigger:
        reasons.append("keyword_trigger")

    if current_mail_scope:
        allowed = explicit_external or explicit_verification
        if not allowed:
            reasons.append("blocked_by_current_mail_scope")
        return VerificationDecision(enabled=allowed, reasons=reasons)

    enabled = explicit_external or explicit_verification or low_confidence_target or keyword_trigger
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


def _is_low_confidence_target(
    intent_task_type: str,
    intent_confidence: float | None,
    model_answer: str,
) -> bool:
    """
    low-confidence/불확실 응답에 대한 외부 검증 대상 여부를 판별한다.

    Args:
        intent_task_type: 의도 task type
        intent_confidence: 의도 confidence
        model_answer: 모델 응답

    Returns:
        검증 대상이면 True
    """
    normalized_task_type = str(intent_task_type or "").strip().lower()
    if normalized_task_type not in {"solution", "retrieval", "analysis"}:
        return False
    confidence = float(intent_confidence) if isinstance(intent_confidence, (int, float)) else 1.0
    if confidence < LOW_CONFIDENCE_THRESHOLD:
        return True
    answer_text = str(model_answer or "").strip().lower()
    if not answer_text:
        return False
    return _contains_any_token(query=answer_text, tokens=UNCERTAINTY_TOKENS)


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
