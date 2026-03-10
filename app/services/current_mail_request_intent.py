from __future__ import annotations

from dataclasses import dataclass

CURRENT_MAIL_ANCHOR_TOKENS: tuple[str, ...] = (
    "현재메일",
    "현재선택메일",
    "현재선택된메일",
    "선택메일",
    "이메일",
    "이메일에서",
    "이메일의",
    "이메일기반",
    "해당메일",
    "이견적",
    "해당견적",
    "이프로젝트",
    "해당프로젝트",
)
CAUSE_OR_EXPLAIN_TOKENS: tuple[str, ...] = ("왜", "원인", "이유", "설명")
PROBLEM_TOKENS: tuple[str, ...] = (
    "문제",
    "이슈",
    "실패",
    "오류",
    "차단",
    "지연",
    "안되",
    "안돼",
    "안됨",
    "불가",
)
SOLUTION_TOKENS: tuple[str, ...] = ("해결", "대응", "방안", "방법")
IMPACT_TOKENS: tuple[str, ...] = ("영향", "파급", "리스크", "차질", "장애")
SUMMARY_TOKENS: tuple[str, ...] = ("요약", "정리")
ROLE_TOKENS: tuple[str, ...] = ("수신자", "발신자", "역할", "담당자")
ERROR_TOKENS: tuple[str, ...] = ("오류", "수신", "재발", "증상")
ESG_TOKENS: tuple[str, ...] = ("esg",)
TOTAL_COST_TOKENS: tuple[str, ...] = ("총예상비용", "총비용", "포함")
REPLY_DRAFT_TOKENS: tuple[str, ...] = ("회신", "답장", "답변메일", "reply")
REPLY_DRAFT_ACTION_TOKENS: tuple[str, ...] = ("초안", "본문", "작성", "써줘", "생성")
ARTIFACT_ANALYSIS_VERBS: tuple[str, ...] = ("분석", "해석", "검토")
ARTIFACT_ANALYSIS_TARGET_TOKENS: tuple[str, ...] = (
    "구문",
    "문법",
    "코드",
    "명령",
    "명령문",
    "쿼리",
    "쿼리문",
    "식",
    "패턴",
    "문자열",
    "필터",
)
RISKY_GUARD_TOKENS: tuple[str, ...] = (
    "문제",
    "누락",
    "이슈",
    "범위",
    "비용",
    "예산",
    "역할",
    "수신자",
    "발신자",
    "담당자",
    "무엇",
    "왜",
    "이유",
    "오류",
    "리스크",
    "후속",
    "esg",
)
CAUSE_ONLY_HINT_TOKENS: tuple[str, ...] = ("원인만", "이유만")
CAUSE_ONLY_FOCUS_TOKENS: tuple[str, ...] = ("원인정리", "이유정리")
DIRECT_FACT_ENTITY_TOKENS: tuple[str, ...] = (
    "메일주소",
    "이메일주소",
    "주소",
    "도메인",
    "계정",
    "발신자",
    "보낸사람",
    "ou",
    "ldap",
    "쿼리",
    "query",
    "명령어",
    "필터",
    "filter",
    "dn",
)
DIRECT_FACT_ASK_TOKENS: tuple[str, ...] = (
    "어떤",
    "무슨",
    "누구",
    "뭐",
    "알려",
)


@dataclass(frozen=True)
class CurrentMailIntentSignals:
    """
    현재메일 이슈 질의의 신호를 정규화한 구조체.

    Attributes:
        has_anchor: 현재메일 앵커 포함 여부
        has_problem: 문제/오류 신호 포함 여부
        has_cause: 원인/설명 신호 포함 여부
        has_response: 대응/해결 신호 포함 여부
        has_impact: 영향 신호 포함 여부
        explicit_cause_only: 원인 전용 요청 여부
    """

    has_anchor: bool
    has_problem: bool
    has_cause: bool
    has_response: bool
    has_impact: bool
    explicit_cause_only: bool


SECTION_POLICY_ORDER: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("cause_only", ("cause",)),
    ("cause_response", ("cause", "response")),
    ("cause_impact", ("cause", "impact")),
    ("response_only", ("response",)),
    ("impact_only", ("impact",)),
    ("cause_default", ("cause", "impact", "response")),
)


def is_current_mail_cause_analysis_request(user_message: str) -> bool:
    """
    현재메일 원인 분석 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        원인 분석 요청이면 True
    """
    signals = _extract_signals(user_message=user_message)
    return signals.has_anchor and signals.has_cause and signals.has_problem


def is_current_mail_solution_request(user_message: str) -> bool:
    """
    현재메일 해결 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        해결 요청이면 True
    """
    signals = _extract_signals(user_message=user_message)
    return signals.has_anchor and signals.has_response


def resolve_current_mail_issue_sections(user_message: str) -> tuple[str, ...]:
    """
    현재메일 이슈 분석 질의의 출력 섹션 계약을 계산한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        섹션 ID 튜플(`cause`, `impact`, `response`)
    """
    signals = _extract_signals(user_message=user_message)
    if not signals.has_anchor or not signals.has_problem:
        return ()
    policy_key = _resolve_section_policy_key(signals=signals)
    return _sections_for_policy(policy_key=policy_key)


def is_current_mail_direct_fact_request(
    user_message: str,
    has_current_mail_context: bool = False,
) -> bool:
    """
    현재메일 맥락에서 특정 항목(주소/도메인/주체)을 직접 묻는 사실질의인지 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        직접 사실질의면 True
    """
    signals = _extract_signals(user_message=user_message)
    has_anchor = signals.has_anchor or bool(has_current_mail_context)
    if not has_anchor:
        return False
    compact = _to_compact(user_message=user_message)
    has_entity_token = any(token in compact for token in DIRECT_FACT_ENTITY_TOKENS)
    has_ask_token = any(token in compact for token in DIRECT_FACT_ASK_TOKENS) or ("?" in str(user_message or ""))
    return has_entity_token and has_ask_token


def is_current_mail_artifact_analysis_request(
    user_message: str,
    has_current_mail_context: bool = False,
) -> bool:
    """
    현재메일 맥락에서 본문 구문(쿼리/명령/코드 등) 분석 요청인지 판별한다.

    Args:
        user_message: 사용자 입력 원문
        has_current_mail_context: 외부 scope에서 current_mail로 이미 확정된 경우 True

    Returns:
        구문 분석 요청이면 True
    """
    signals = _extract_signals(user_message=user_message)
    has_anchor = signals.has_anchor or bool(has_current_mail_context)
    if not has_anchor:
        return False
    compact = _to_compact(user_message=user_message)
    has_analysis_verb = any(token in compact for token in ARTIFACT_ANALYSIS_VERBS)
    if not has_analysis_verb:
        return False
    return any(token in compact for token in ARTIFACT_ANALYSIS_TARGET_TOKENS)


def _has_current_mail_anchor(compact: str) -> bool:
    """
    현재메일 문맥 앵커 포함 여부를 판별한다.

    Args:
        compact: 공백 제거/소문자 정규화 문자열

    Returns:
        앵커 포함 시 True
    """
    return any(token in compact for token in CURRENT_MAIL_ANCHOR_TOKENS)


def _to_compact(user_message: str) -> str:
    """
    질의 문자열을 판별용으로 정규화한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        공백 제거 + 소문자 문자열
    """
    return str(user_message or "").replace(" ", "").lower()


def _extract_signals(user_message: str) -> CurrentMailIntentSignals:
    """
    현재메일 질의 문자열에서 이슈 섹션 라우팅 신호를 추출한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        정규화된 현재메일 의도 신호
    """
    compact = _to_compact(user_message=user_message)
    has_anchor = _has_current_mail_anchor(compact=compact)
    has_problem = any(token in compact for token in PROBLEM_TOKENS)
    has_cause = any(token in compact for token in CAUSE_OR_EXPLAIN_TOKENS)
    has_response = any(token in compact for token in SOLUTION_TOKENS)
    has_impact = any(token in compact for token in IMPACT_TOKENS)
    explicit_cause_only = _is_explicit_cause_only(compact=compact, has_response=has_response, has_impact=has_impact)
    return CurrentMailIntentSignals(
        has_anchor=has_anchor,
        has_problem=has_problem,
        has_cause=has_cause,
        has_response=has_response,
        has_impact=has_impact,
        explicit_cause_only=explicit_cause_only,
    )


def _is_explicit_cause_only(compact: str, has_response: bool, has_impact: bool) -> bool:
    """
    원인 전용 요청 여부를 판단한다.

    Args:
        compact: 공백 제거/소문자 정규화 문자열
        has_response: 대응 신호 여부
        has_impact: 영향 신호 여부

    Returns:
        원인 전용 요청이면 True
    """
    cause_only_hint = any(token in compact for token in CAUSE_ONLY_HINT_TOKENS)
    cause_focus = any(token in compact for token in CAUSE_ONLY_FOCUS_TOKENS)
    return (cause_only_hint or cause_focus) and not has_response and not has_impact


def _resolve_section_policy_key(signals: CurrentMailIntentSignals) -> str:
    """
    현재메일 이슈 신호를 섹션 정책 키로 변환한다.

    Args:
        signals: 정규화 의도 신호

    Returns:
        섹션 정책 키 문자열
    """
    if signals.explicit_cause_only:
        return "cause_only"
    if signals.has_cause and signals.has_response and not signals.has_impact:
        return "cause_response"
    if signals.has_cause and signals.has_impact and not signals.has_response:
        return "cause_impact"
    if signals.has_response and not signals.has_cause and not signals.has_impact:
        return "response_only"
    if signals.has_impact and not signals.has_cause and not signals.has_response:
        return "impact_only"
    return "cause_default"


def _sections_for_policy(policy_key: str) -> tuple[str, ...]:
    """
    섹션 정책 키에 대응하는 섹션 계약을 조회한다.

    Args:
        policy_key: 섹션 정책 키

    Returns:
        섹션 ID 튜플
    """
    for key, sections in SECTION_POLICY_ORDER:
        if key == policy_key:
            return sections
    return ("cause", "impact", "response")


def should_apply_current_mail_grounded_safe_guard(user_message: str) -> bool:
    """
    현재메일 저근거 안전가드를 적용할지 공통 정책으로 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        안전가드 적용 대상이면 True
    """
    compact = _to_compact(user_message=user_message)
    if not compact:
        return False
    if _is_reply_draft_focused_request(compact=compact):
        return False
    if _is_summary_focused_request(compact=compact):
        return False
    return any(token in compact for token in RISKY_GUARD_TOKENS)


def render_current_mail_grounded_safe_message(user_message: str, summary_text: str) -> str:
    """
    현재메일 저근거 상황에서 의도 정합 안전응답 문구를 생성한다.

    Args:
        user_message: 사용자 입력 원문
        summary_text: 현재메일 요약 텍스트

    Returns:
        의도 기반 안전응답
    """
    compact = _to_compact(user_message=user_message)
    safe_summary = str(summary_text or "").strip()[:240]
    if any(token in compact for token in ROLE_TOKENS):
        return (
            f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
            "현재 근거(subject/snippet)에는 발신자·수신자·역할 정보가 없어 해당 항목은 확인할 수 없습니다."
        )
    if any(token in compact for token in CAUSE_OR_EXPLAIN_TOKENS):
        return (
            f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
            "근거에는 '라이선스 확인 필요'만 기재되어 있어 별도 확인이 필요한 구체적 이유는 확인할 수 없습니다."
        )
    if any(token in compact for token in ERROR_TOKENS):
        return (
            f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
            "현재 근거에는 수신 오류 증상/원인/재발방지 정보가 없어 해당 내용은 확인할 수 없습니다."
        )
    if any(token in compact for token in ESG_TOKENS):
        return (
            f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
            "현재 메일은 ESG 프로젝트 메일이 아니므로 ESG 관련 진행 상황/이슈는 확인할 수 없습니다."
        )
    if any(token in compact for token in TOTAL_COST_TOKENS):
        return (
            f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
            "현재 근거 기준으로 확인 가능한 금액은 총 193,000,000원(라이선스 별도 확인 필요)이며, 포함 총액은 확정할 수 없습니다."
        )
    return (
        f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
        "질문과 직접 관련된 세부 항목은 현재 근거만으로 확인할 수 없습니다."
    )


def _is_summary_focused_request(compact: str) -> bool:
    """
    요약 중심 질의인지 판별한다.

    Args:
        compact: 공백 제거/소문자 정규화 문자열

    Returns:
        요약 중심 질의면 True
    """
    has_summary = any(token in compact for token in SUMMARY_TOKENS)
    if not has_summary:
        return False
    high_risk = (
        PROBLEM_TOKENS
        + ROLE_TOKENS
        + CAUSE_OR_EXPLAIN_TOKENS
        + ERROR_TOKENS
        + TOTAL_COST_TOKENS
        + IMPACT_TOKENS
    )
    return not any(token in compact for token in high_risk)


def _is_reply_draft_focused_request(compact: str) -> bool:
    """
    회신/답장 본문 초안 생성 요청인지 판별한다.

    Args:
        compact: 공백 제거/소문자 정규화 문자열

    Returns:
        회신 초안 작성 질의면 True
    """
    has_reply = any(token in compact for token in REPLY_DRAFT_TOKENS)
    has_action = any(token in compact for token in REPLY_DRAFT_ACTION_TOKENS)
    return has_reply and has_action
