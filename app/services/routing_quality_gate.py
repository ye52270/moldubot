from __future__ import annotations

from typing import Any


KPI_BASELINE_THRESHOLDS: dict[str, float] = {
    "intent_required_steps_pass_rate": 95.0,
    "intent_parse_success_rate": 99.0,
    "summary_line_compliance_rate": 95.0,
    "report_format_compliance_rate": 90.0,
    "booking_failure_reason_compliance_rate": 90.0,
    "chat_success_rate": 95.0,
    "avg_latency_ms": 6500.0,
}


def evaluate_routing_quality_gate(
    intent_summary: dict[str, Any],
    chat_summary: dict[str, Any],
    thresholds: dict[str, float] | None = None,
) -> dict[str, Any]:
    """
    intent/chat 품질 요약 지표를 기준선과 비교해 회귀 게이트 통과 여부를 판정한다.

    Args:
        intent_summary: intent 평가 요약 지표
        chat_summary: chat 품질 평가 요약 지표
        thresholds: 커스텀 임계치(미지정 시 기본 임계치)

    Returns:
        게이트 판정 결과 사전
    """
    active_thresholds = dict(KPI_BASELINE_THRESHOLDS)
    if isinstance(thresholds, dict):
        active_thresholds.update(thresholds)
    checks = {
        "intent_required_steps_pass_rate": float(intent_summary.get("required_steps_pass_rate", 0.0)),
        "intent_parse_success_rate": float(intent_summary.get("parse_success_rate", 0.0)),
        "summary_line_compliance_rate": float(chat_summary.get("summary_line_compliance_rate", 0.0)),
        "report_format_compliance_rate": float(chat_summary.get("report_format_compliance_rate", 0.0)),
        "booking_failure_reason_compliance_rate": float(chat_summary.get("booking_failure_reason_compliance_rate", 0.0)),
        "chat_success_rate": float(chat_summary.get("success_rate", 0.0)),
        "avg_latency_ms": float(chat_summary.get("avg_elapsed_ms", 0.0)),
    }
    breaches: list[dict[str, Any]] = []
    for key, value in checks.items():
        threshold = float(active_thresholds.get(key, 0.0))
        if key == "avg_latency_ms":
            if value > threshold:
                breaches.append({"metric": key, "value": value, "threshold": threshold, "direction": "max"})
            continue
        if value < threshold:
            breaches.append({"metric": key, "value": value, "threshold": threshold, "direction": "min"})

    return {
        "passed": len(breaches) == 0,
        "checks": checks,
        "thresholds": active_thresholds,
        "breaches": breaches,
    }
