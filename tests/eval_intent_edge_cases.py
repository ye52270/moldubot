from __future__ import annotations

import json
import time
from statistics import mean
from typing import Any

from app.agents.intent_parser import get_intent_parser
from tests.fixtures.intent_query_edge_cases import INTENT_EDGE_CASES


def _is_date_filter_match(actual: dict[str, Any], expected: dict[str, Any]) -> bool:
    """
    날짜 필터를 부분 필드 기준으로 비교한다.

    Args:
        actual: 실제 파서 결과의 date_filter
        expected: 케이스에서 정의한 기대 date_filter

    Returns:
        기대 필드가 모두 일치하면 True
    """
    for key, expected_value in expected.items():
        actual_value = actual.get(key, "")
        if hasattr(actual_value, "value"):
            actual_value = getattr(actual_value, "value")
        if str(actual_value) != str(expected_value):
            return False
    return True


def evaluate_intent_edge_cases() -> dict[str, Any]:
    """
    경계 케이스 20개를 실행해 의도 분해 품질 지표를 계산한다.

    Returns:
        케이스별 결과와 요약 지표를 포함한 사전
    """
    parser = get_intent_parser()
    per_case: list[dict[str, Any]] = []
    elapsed_list: list[float] = []
    steps_pass = 0
    summary_pass = 0
    date_pass = 0
    missing_pass = 0
    all_pass = 0

    for case in INTENT_EDGE_CASES:
        start = time.perf_counter()
        decomposition = parser.parse(case["utterance"])
        elapsed_ms = round((time.perf_counter() - start) * 1000, 1)
        elapsed_list.append(elapsed_ms)

        actual = decomposition.model_dump()
        actual_steps = actual["steps"]
        actual_summary = actual["summary_line_target"]
        actual_date = actual["date_filter"]
        actual_missing = actual["missing_slots"]

        steps_ok = actual_steps == case["expected_steps"]
        summary_ok = actual_summary == case["expected_summary_line_target"]
        date_ok = _is_date_filter_match(actual=actual_date, expected=case["expected_date_filter"])
        missing_ok = actual_missing == case["expected_missing_slots"]
        passed = steps_ok and summary_ok and date_ok and missing_ok

        steps_pass += int(steps_ok)
        summary_pass += int(summary_ok)
        date_pass += int(date_ok)
        missing_pass += int(missing_ok)
        all_pass += int(passed)

        per_case.append(
            {
                "case_id": case["case_id"],
                "pattern": case["pattern"],
                "utterance": case["utterance"],
                "elapsed_ms": elapsed_ms,
                "passed": passed,
                "checks": {
                    "steps": steps_ok,
                    "summary_line_target": summary_ok,
                    "date_filter": date_ok,
                    "missing_slots": missing_ok,
                },
                "actual": {
                    "steps": actual_steps,
                    "summary_line_target": actual_summary,
                    "date_filter": actual_date,
                    "missing_slots": actual_missing,
                },
                "expected": {
                    "steps": case["expected_steps"],
                    "summary_line_target": case["expected_summary_line_target"],
                    "date_filter": case["expected_date_filter"],
                    "missing_slots": case["expected_missing_slots"],
                },
            }
        )

    total = len(INTENT_EDGE_CASES)
    return {
        "summary": {
            "total": total,
            "passed_all_fields": all_pass,
            "accuracy_all_fields": round((all_pass / total) * 100, 1),
            "accuracy_steps": round((steps_pass / total) * 100, 1),
            "accuracy_summary_line_target": round((summary_pass / total) * 100, 1),
            "accuracy_date_filter": round((date_pass / total) * 100, 1),
            "accuracy_missing_slots": round((missing_pass / total) * 100, 1),
            "avg_elapsed_ms": round(mean(elapsed_list), 1),
            "max_elapsed_ms": max(elapsed_list),
            "min_elapsed_ms": min(elapsed_list),
        },
        "cases": per_case,
    }


if __name__ == "__main__":
    # CI/로컬에서 바로 읽기 쉽도록 JSON으로 출력한다.
    result = evaluate_intent_edge_cases()
    print(json.dumps(result, ensure_ascii=False, indent=2))
