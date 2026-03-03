from __future__ import annotations

import json
import logging
import re
import time
from statistics import mean
from urllib import error, request

from tests.fixtures.chat_quality_cases import CHAT_QUALITY_CASES

DEFAULT_CHAT_URL = "http://127.0.0.1:8000/search/chat"
DEFAULT_REQUEST_TIMEOUT_SEC = 90
BOOKING_REASON_KEYWORDS = (
    "과거 날짜",
    "동일 시간대",
    "정원",
    "찾지 못",
    "유효하지 않은",
    "추가 필요 슬롯",
    "정보가 부족",
)


logger = logging.getLogger(__name__)


def run_chat_quality_cases(
    chat_url: str = DEFAULT_CHAT_URL,
    request_timeout_sec: int = DEFAULT_REQUEST_TIMEOUT_SEC,
    max_cases: int | None = None,
) -> dict[str, object]:
    """
    채팅 품질 10문장 케이스를 `/search/chat`에 실호출해 결과를 수집한다.

    Args:
        chat_url: 채팅 API 엔드포인트 URL
        request_timeout_sec: 케이스별 HTTP 타임아웃(초)
        max_cases: 실행할 최대 케이스 수(미지정 시 전체)

    Returns:
        케이스별 결과와 요약 지표를 담은 사전
    """
    per_case: list[dict[str, object]] = []
    elapsed_list: list[float] = []

    active_cases = CHAT_QUALITY_CASES[: max_cases] if isinstance(max_cases, int) and max_cases > 0 else CHAT_QUALITY_CASES

    for case in active_cases:
        payload = {"message": case["utterance"]}
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        req = request.Request(
            chat_url,
            data=body,
            headers={"content-type": "application/json"},
            method="POST",
        )

        started_at = time.perf_counter()
        try:
            with request.urlopen(req, timeout=max(1, int(request_timeout_sec))) as resp:
                status_code = int(resp.getcode())
                data = json.loads(resp.read().decode("utf-8"))
        except error.URLError as exc:
            elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
            elapsed_list.append(elapsed_ms)
            per_case.append(
                {
                    "case_id": case["case_id"],
                    "pattern": case["pattern"],
                    "utterance": case["utterance"],
                    "status_code": 0,
                    "elapsed_ms": elapsed_ms,
                    "success": False,
                    "source": "request-error",
                    "answer": "",
                    "error": str(exc),
                }
            )
            continue

        elapsed_ms = round((time.perf_counter() - started_at) * 1000, 1)
        elapsed_list.append(elapsed_ms)
        answer = str(data.get("answer") or "").strip()
        source = str(data.get("metadata", {}).get("source") or "")
        success = status_code == 200 and bool(answer)
        per_case.append(
            {
                "case_id": case["case_id"],
                "pattern": case["pattern"],
                "utterance": case["utterance"],
                "status_code": status_code,
                "elapsed_ms": elapsed_ms,
                "success": success,
                "source": source,
                "answer_length": len(answer),
                "answer": answer,
            }
        )

    quality = _build_quality_metrics(per_case=per_case)
    total = len(per_case)
    success_count = sum(1 for item in per_case if item.get("success"))
    return {
        "summary": {
            "total": total,
            "success_count": success_count,
            "success_rate": round((success_count / total) * 100, 1) if total else 0.0,
            "avg_elapsed_ms": round(mean(elapsed_list), 1) if elapsed_list else 0.0,
            "max_elapsed_ms": max(elapsed_list) if elapsed_list else 0.0,
            "min_elapsed_ms": min(elapsed_list) if elapsed_list else 0.0,
            **quality,
        },
        "cases": per_case,
    }


def _build_quality_metrics(per_case: list[dict[str, object]]) -> dict[str, object]:
    """
    응답 본문 기준의 자동 품질 판정 지표를 집계한다.

    Args:
        per_case: 케이스별 실행 결과 목록

    Returns:
        요약 줄수/보고서 형식/예약 실패 사유 정합성 지표
    """
    summary_checks: list[bool] = []
    report_checks: list[bool] = []
    booking_reason_checks: list[bool] = []

    for item in per_case:
        utterance = str(item.get("utterance") or "")
        answer = str(item.get("answer") or "")
        if _is_summary_line_case(utterance=utterance):
            summary_checks.append(_is_summary_line_target_compliant(utterance=utterance, answer=answer))
        if _is_report_case(utterance=utterance):
            report_checks.append(_is_report_format_compliant(answer=answer))
        if _is_booking_case(utterance=utterance):
            booking_reason_checks.append(_is_booking_failure_reason_compliant(answer=answer))

    return {
        "summary_line_compliance_rate": _to_rate(checked=summary_checks),
        "summary_line_checked_cases": len(summary_checks),
        "report_format_compliance_rate": _to_rate(checked=report_checks),
        "report_format_checked_cases": len(report_checks),
        "booking_failure_reason_compliance_rate": _to_rate(checked=booking_reason_checks),
        "booking_failure_reason_checked_cases": len(booking_reason_checks),
    }


def _is_summary_line_case(utterance: str) -> bool:
    """
    발화가 줄수 기반 요약 검증 대상인지 판별한다.

    Args:
        utterance: 사용자 발화

    Returns:
        요약 줄수 검증 대상이면 True
    """
    return bool(re.search(r"\d{1,2}\s*줄", utterance)) and ("요약" in utterance)


def _is_report_case(utterance: str) -> bool:
    """
    발화가 보고서 형식 검증 대상인지 판별한다.

    Args:
        utterance: 사용자 발화

    Returns:
        보고서 검증 대상이면 True
    """
    return "보고서" in utterance


def _is_booking_case(utterance: str) -> bool:
    """
    발화가 예약 실패 사유 검증 대상인지 판별한다.

    Args:
        utterance: 사용자 발화

    Returns:
        예약 검증 대상이면 True
    """
    return "예약" in utterance


def _is_summary_line_target_compliant(utterance: str, answer: str) -> bool:
    """
    요약 응답이 요청 줄수 이내인지 판정한다.

    Args:
        utterance: 사용자 발화
        answer: 모델 응답

    Returns:
        요청 줄수 이하이면 True
    """
    target = _extract_summary_target(utterance=utterance)
    if target is None:
        return True
    line_count = _count_numbered_summary_lines(answer=answer)
    if line_count == 0:
        line_count = _count_non_empty_lines(answer=answer)
    return line_count <= target


def _extract_summary_target(utterance: str) -> int | None:
    """
    발화에서 요약 줄수 목표를 추출한다.

    Args:
        utterance: 사용자 발화

    Returns:
        추출된 줄수 또는 None
    """
    matched = re.search(r"(\d{1,2})\s*줄", utterance)
    if not matched:
        return None
    return int(matched.group(1))


def _count_numbered_summary_lines(answer: str) -> int:
    """
    응답 내 번호형 요약 라인 개수를 센다.

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
        보고서 키워드 또는 구조적 라인(헤더/불릿)이 있으면 True
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
        실패가 아니면 True, 실패일 때는 사유 키워드 포함 시 True
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
        0~100 백분율(소수점 1자리)
    """
    if not checked:
        return 100.0
    success = sum(1 for item in checked if item)
    return round((success / len(checked)) * 100, 1)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    result = run_chat_quality_cases()
    logger.info("chat_quality_eval=%s", json.dumps(result, ensure_ascii=False, indent=2))
