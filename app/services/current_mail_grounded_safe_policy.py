from __future__ import annotations


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
    risk_terms = ("문제", "누락", "이슈", "범위", "비용", "예산", "역할", "오류", "리스크", "후속", "왜", "이유")
    return _contains_any(compact, risk_terms)


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
    if _contains_any(compact, ("수신자", "발신자", "역할", "담당자")):
        return (
            f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
            "현재 근거(subject/snippet)에는 발신자·수신자·역할 정보가 없어 해당 항목은 확인할 수 없습니다."
        )
    if _contains_any(compact, ("왜", "원인", "이유", "설명")):
        return (
            f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
            "근거에는 '라이선스 확인 필요'만 기재되어 있어 별도 확인이 필요한 구체적 이유는 확인할 수 없습니다."
        )
    if _contains_any(compact, ("오류", "수신", "재발", "증상")):
        return (
            f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
            "현재 근거에는 수신 오류 증상/원인/재발방지 정보가 없어 해당 내용은 확인할 수 없습니다."
        )
    if "esg" in compact:
        return (
            f"현재 메일 근거에서 확인되는 내용: {safe_summary}\n"
            "현재 메일은 ESG 프로젝트 메일이 아니므로 ESG 관련 진행 상황/이슈는 확인할 수 없습니다."
        )
    if _contains_any(compact, ("총예상비용", "총비용", "포함")):
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
    has_summary = _contains_any(compact, ("요약", "정리"))
    if not has_summary:
        return False
    high_risk = ("문제", "이슈", "실패", "오류", "역할", "수신자", "발신자", "원인", "이유", "총비용", "영향", "리스크")
    return not _contains_any(compact, high_risk)


def _is_reply_draft_focused_request(compact: str) -> bool:
    """
    회신/답장 본문 초안 생성 요청인지 판별한다.

    Args:
        compact: 공백 제거/소문자 정규화 문자열

    Returns:
        회신 초안 작성 질의면 True
    """
    has_reply = _contains_any(compact, ("회신", "답장", "답변메일", "reply"))
    has_action = _contains_any(compact, ("초안", "본문", "작성", "써줘", "생성"))
    return has_reply and has_action


def _contains_any(text: str, terms: tuple[str, ...]) -> bool:
    """
    텍스트에 후보 문자열이 하나라도 포함되는지 판별한다.

    Args:
        text: 검사 대상 문자열
        terms: 포함 여부를 검사할 후보 문자열 목록

    Returns:
        하나라도 포함되면 True
    """
    return any(term in text for term in terms)


def _to_compact(user_message: str) -> str:
    """
    질의 문자열을 판별용으로 정규화한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        공백 제거 + 소문자 문자열
    """
    return str(user_message or "").replace(" ", "").lower()
