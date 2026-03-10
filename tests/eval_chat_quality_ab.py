from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass
from typing import Any

from tests.eval_chat_quality_cases import DEFAULT_CHAT_URL, run_chat_quality_cases

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class EvalTarget:
    """
    A/B 평가 대상 서버 정의.

    Attributes:
        name: 평가 대상 이름
        chat_url: `/search/chat` 엔드포인트 URL
    """

    name: str
    chat_url: str


def _to_float(value: Any) -> float:
    """
    숫자 입력을 float로 정규화한다.

    Args:
        value: 원본 값

    Returns:
        변환된 float 값
    """

    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _summary_of(result: dict[str, Any]) -> dict[str, float]:
    """
    채팅 품질 실행 결과에서 요약 지표를 추출한다.

    Args:
        result: `run_chat_quality_cases` 실행 결과

    Returns:
        핵심 지표 사전
    """

    summary = result.get("summary", {}) if isinstance(result, dict) else {}
    return {
        "success_rate": _to_float(summary.get("success_rate")),
        "avg_elapsed_ms": _to_float(summary.get("avg_elapsed_ms")),
        "summary_line_compliance_rate": _to_float(summary.get("summary_line_compliance_rate")),
        "report_format_compliance_rate": _to_float(summary.get("report_format_compliance_rate")),
        "booking_failure_reason_compliance_rate": _to_float(
            summary.get("booking_failure_reason_compliance_rate")
        ),
    }


def build_ab_delta(
    baseline: dict[str, Any],
    candidate: dict[str, Any],
) -> dict[str, float]:
    """
    baseline 대비 candidate의 핵심 지표 변화량을 계산한다.

    Args:
        baseline: baseline 실행 결과
        candidate: candidate 실행 결과

    Returns:
        지표별 delta 사전(candidate - baseline)
    """

    base = _summary_of(baseline)
    cand = _summary_of(candidate)
    return {
        "delta_success_rate": round(cand["success_rate"] - base["success_rate"], 1),
        "delta_avg_elapsed_ms": round(cand["avg_elapsed_ms"] - base["avg_elapsed_ms"], 1),
        "delta_summary_line_compliance_rate": round(
            cand["summary_line_compliance_rate"] - base["summary_line_compliance_rate"],
            1,
        ),
        "delta_report_format_compliance_rate": round(
            cand["report_format_compliance_rate"] - base["report_format_compliance_rate"],
            1,
        ),
        "delta_booking_failure_reason_compliance_rate": round(
            cand["booking_failure_reason_compliance_rate"]
            - base["booking_failure_reason_compliance_rate"],
            1,
        ),
    }


def run_chat_quality_ab(
    baseline_target: EvalTarget,
    candidate_target: EvalTarget,
) -> dict[str, Any]:
    """
    두 대상 서버를 동일 품질 케이스로 A/B 평가한다.

    Args:
        baseline_target: 기준 서버
        candidate_target: 비교 서버

    Returns:
        baseline/candidate 결과와 delta를 포함한 사전
    """

    baseline_result = run_chat_quality_cases(chat_url=baseline_target.chat_url)
    candidate_result = run_chat_quality_cases(chat_url=candidate_target.chat_url)
    delta = build_ab_delta(baseline=baseline_result, candidate=candidate_result)
    return {
        "baseline": {
            "name": baseline_target.name,
            "chat_url": baseline_target.chat_url,
            **baseline_result,
        },
        "candidate": {
            "name": candidate_target.name,
            "chat_url": candidate_target.chat_url,
            **candidate_result,
        },
        "delta": delta,
    }


def _load_targets_from_env() -> tuple[EvalTarget, EvalTarget]:
    """
    환경변수에서 A/B 평가 대상을 읽어 반환한다.

    Returns:
        baseline/candidate 대상 튜플
    """

    baseline_url = str(os.getenv("MOLDUBOT_CHAT_URL_BASELINE", DEFAULT_CHAT_URL)).strip() or DEFAULT_CHAT_URL
    candidate_url = str(os.getenv("MOLDUBOT_CHAT_URL_CANDIDATE", DEFAULT_CHAT_URL)).strip() or DEFAULT_CHAT_URL
    baseline_name = str(os.getenv("MOLDUBOT_CHAT_NAME_BASELINE", "baseline")).strip() or "baseline"
    candidate_name = str(os.getenv("MOLDUBOT_CHAT_NAME_CANDIDATE", "candidate")).strip() or "candidate"
    return EvalTarget(name=baseline_name, chat_url=baseline_url), EvalTarget(
        name=candidate_name,
        chat_url=candidate_url,
    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    baseline, candidate = _load_targets_from_env()
    result = run_chat_quality_ab(baseline_target=baseline, candidate_target=candidate)
    logger.info("chat_quality_ab=%s", json.dumps(result, ensure_ascii=False, indent=2))
