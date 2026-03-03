from __future__ import annotations

import re
from typing import Any

BOOKING_REASON_KEYWORDS = (
    "과거 날짜",
    "동일 시간대",
    "정원",
    "찾지 못",
    "유효하지 않은",
    "추가 필요 슬롯",
    "정보가 부족",
)


def build_quality_metrics(per_case: list[dict[str, Any]]) -> dict[str, Any]:
    """
    케이스 목록에서 자동 품질 지표를 집계한다.

    Args:
        per_case: 케이스별 질의/응답 목록

    Returns:
        요약 줄수/보고서 형식/예약 실패 사유 정합성 지표
    """
    summary_checks: list[bool] = []
    report_checks: list[bool] = []
    booking_reason_checks: list[bool] = []

    for item in per_case:
        query = str(item.get("query") or item.get("utterance") or "")
        answer = str(item.get("answer") or "")
        if _is_summary_line_case(query=query):
            summary_checks.append(_is_summary_line_target_compliant(query=query, answer=answer))
        if _is_report_case(query=query):
            report_checks.append(_is_report_format_compliant(answer=answer))
        if _is_booking_case(query=query):
            booking_reason_checks.append(_is_booking_failure_reason_compliant(answer=answer))

    return {
        "summary_line_compliance_rate": _to_rate(checked=summary_checks),
        "summary_line_checked_cases": len(summary_checks),
        "report_format_compliance_rate": _to_rate(checked=report_checks),
        "report_format_checked_cases": len(report_checks),
        "booking_failure_reason_compliance_rate": _to_rate(checked=booking_reason_checks),
        "booking_failure_reason_checked_cases": len(booking_reason_checks),
    }


def _is_summary_line_case(query: str) -> bool:
    """
    질의가 줄수 기반 요약 검증 대상인지 판별한다.

    Args:
        query: 사용자 질의

    Returns:
        요약 줄수 검증 대상 여부
    """
    return bool(re.search(r"\d{1,2}\s*줄", query)) and ("요약" in query)


def _is_report_case(query: str) -> bool:
    """
    질의가 보고서 형식 검증 대상인지 판별한다.

    Args:
        query: 사용자 질의

    Returns:
        보고서 검증 대상 여부
    """
    return "보고서" in query


def _is_booking_case(query: str) -> bool:
    """
    질의가 예약 실패 사유 검증 대상인지 판별한다.

    Args:
        query: 사용자 질의

    Returns:
        예약 검증 대상 여부
    """
    return "예약" in query


def _is_summary_line_target_compliant(query: str, answer: str) -> bool:
    """
    요약 응답이 요청 줄수 이내인지 판정한다.

    Args:
        query: 사용자 질의
        answer: 모델 응답

    Returns:
        요청 줄수 이하 여부
    """
    target = _extract_summary_target(query=query)
    if target is None:
        return True
    line_count = _count_numbered_summary_lines(answer=answer)
    if line_count == 0:
        line_count = _count_non_empty_lines(answer=answer)
    return line_count <= target


def _extract_summary_target(query: str) -> int | None:
    """
    질의에서 요약 줄수 목표를 추출한다.

    Args:
        query: 사용자 질의

    Returns:
        추출된 줄수 또는 None
    """
    matched = re.search(r"(\d{1,2})\s*줄", query)
    if not matched:
        return None
    return int(matched.group(1))


def _count_numbered_summary_lines(answer: str) -> int:
    """
    응답 내 번호형 라인 개수를 센다.

    Args:
        answer: 모델 응답

    Returns:
        번호형 줄 개수
    """
    lines = [line.strip() for line in str(answer or "").split("\n") if line.strip()]
    return sum(1 for line in lines if re.match(r"^\d+[.)]\s+", line) is not None)


def _count_non_empty_lines(answer: str) -> int:
    """
    응답 내 공백 제외 라인 개수를 센다.

    Args:
        answer: 모델 응답

    Returns:
        공백 제외 줄 개수
    """
    return len([line for line in str(answer or "").split("\n") if line.strip()])


def _is_report_format_compliant(answer: str) -> bool:
    """
    보고서 응답이 기본 포맷 조건을 만족하는지 판정한다.

    Args:
        answer: 모델 응답

    Returns:
        보고서 형식 충족 여부
    """
    text = str(answer or "").strip()
    if not text:
        return False
    if "보고서" in text:
        return True
    lines = [line.strip() for line in text.split("\n") if line.strip()]
    has_header = any(line.startswith("#") for line in lines)
    has_bullet = any(line.startswith("- ") or line.startswith("* ") for line in lines)
    return has_header or has_bullet


def _is_booking_failure_reason_compliant(answer: str) -> bool:
    """
    예약 실패 응답이 실패 사유 키워드를 포함하는지 판정한다.

    Args:
        answer: 모델 응답

    Returns:
        실패가 아니면 True, 실패일 때는 사유 키워드 포함 여부
    """
    text = str(answer or "").strip()
    if "예약 실패" not in text:
        return True
    return any(keyword in text for keyword in BOOKING_REASON_KEYWORDS)


def _to_rate(checked: list[bool]) -> float:
    """
    불리언 판정 목록을 백분율로 변환한다.

    Args:
        checked: 판정 결과 목록

    Returns:
        0~100 백분율
    """
    if not checked:
        return 100.0
    success = sum(1 for item in checked if item)
    return round((success / len(checked)) * 100, 1)
