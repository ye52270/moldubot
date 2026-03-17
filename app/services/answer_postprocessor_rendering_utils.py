from __future__ import annotations

from app.services.answer_postprocessor_summary import split_headline_and_detail


def collect_standard_summary_missing_fields(
    subject: str,
    sender: str,
    recipient: str,
    date_text: str,
    core_issue: str,
    major_points: list[str],
    required_actions: list[str],
    one_line_summary: str,
) -> list[str]:
    """
    표준 요약 출력의 필수 필드 누락 목록을 수집한다.

    Args:
        subject: 제목 텍스트
        sender: 발신자
        recipient: 수신자
        date_text: 날짜
        core_issue: 핵심 이슈
        major_points: 주요 내용 목록
        required_actions: 조치 필요 사항 목록
        one_line_summary: 1줄 요약

    Returns:
        누락 필드 이름 목록
    """
    missing: list[str] = []
    if not subject or subject in ("-", "제목 정보 없음"):
        missing.append("title")
    if not sender or sender == "-":
        missing.append("sender")
    if not recipient or recipient == "-":
        missing.append("recipient")
    if not date_text or date_text == "-":
        missing.append("date")
    if not core_issue:
        missing.append("core_issue")
    if not major_points:
        missing.append("major_points")
    if not required_actions:
        missing.append("required_actions")
    if not one_line_summary:
        missing.append("one_line_summary")
    return missing


def render_major_points(major_points: list[str]) -> list[str]:
    """
    주요 내용 목록을 사용자 읽기 쉬운 번호/불릿 블록으로 변환한다.

    Args:
        major_points: 주요 내용 목록

    Returns:
        렌더링 라인 목록
    """
    rendered: list[str] = []
    for index, point in enumerate(major_points, start=1):
        raw_point = str(point or "").strip()
        if any(delimiter in raw_point for delimiter in (" — ", " - ", ": ")):
            headline, detail = split_headline_and_detail(line=raw_point)
        else:
            headline, detail = raw_point, ""
        if headline.strip() == "근거" and detail:
            rendered.append(f"{index}. 근거: {detail}")
            continue
        rendered.append(f"{index}. {headline}")
        if not detail:
            continue
        if _is_effectively_same_line(headline=headline, detail=detail):
            continue
        if "전달 경로" in headline and detail:
            rendered.append("```")
            rendered.append(detail)
            rendered.append("```")
        else:
            rendered.append(f"- {detail}" if detail else f"- {point}")
    return rendered


def _is_effectively_same_line(headline: str, detail: str) -> bool:
    """
    headline과 detail이 사실상 동일 문장인지 판별한다.

    Args:
        headline: 요약 헤드라인
        detail: 세부 설명

    Returns:
        공백/구두점/구분기호를 제거했을 때 동일하면 True
    """
    normalized_headline = _normalize_compare_text(value=headline)
    normalized_detail = _normalize_compare_text(value=detail)
    if not normalized_headline or not normalized_detail:
        return False
    return normalized_headline == normalized_detail


def _normalize_compare_text(value: str) -> str:
    """
    문장 비교를 위한 정규화 문자열을 생성한다.

    Args:
        value: 원문 문자열

    Returns:
        비교용 정규화 문자열
    """
    text = str(value or "").strip().lower()
    if not text:
        return ""
    cleaned = (
        text.replace(" ", "")
        .replace("—", "")
        .replace("-", "")
        .replace(":", "")
        .replace(".", "")
        .replace(",", "")
        .replace(";", "")
        .replace("|", "")
        .replace("(", "")
        .replace(")", "")
    )
    return cleaned


def render_required_actions(required_actions: list[str]) -> list[str]:
    """
    조치 필요 사항 목록을 번호 리스트 라인으로 변환한다.

    Args:
        required_actions: 조치 필요 사항 목록

    Returns:
        렌더링 라인 목록
    """
    return [f"{index}. {item}" for index, item in enumerate(required_actions, start=1)]
