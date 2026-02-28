from __future__ import annotations

import argparse
import json
import time
from statistics import mean
from typing import Any

from app.agents.intent_parser import get_intent_parser
from app.agents.intent_schema import DateFilter, DateFilterMode, ExecutionStep, IntentDecomposition
from app.core.intent_rules import (
    build_missing_slots,
    extract_date_filter_fields,
    extract_summary_line_target,
    infer_steps_from_query,
    sanitize_user_query,
)
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


def _map_step_value(step_value: str) -> ExecutionStep | None:
    """
    문자열 step 값을 ExecutionStep enum으로 변환한다.

    Args:
        step_value: step 문자열 값

    Returns:
        변환된 ExecutionStep 또는 None
    """
    mapping = {
        "read_current_mail": ExecutionStep.READ_CURRENT_MAIL,
        "summarize_mail": ExecutionStep.SUMMARIZE_MAIL,
        "extract_key_facts": ExecutionStep.EXTRACT_KEY_FACTS,
        "extract_recipients": ExecutionStep.EXTRACT_RECIPIENTS,
        "search_meeting_schedule": ExecutionStep.SEARCH_MEETING_SCHEDULE,
        "book_meeting_room": ExecutionStep.BOOK_MEETING_ROOM,
    }
    return mapping.get(step_value)


def _build_rule_only_decomposition(user_message: str) -> IntentDecomposition:
    """
    모델 호출 없이 규칙 모듈만으로 의도 구조분해 결과를 생성한다.

    Args:
        user_message: 사용자 입력 문장

    Returns:
        규칙 기반 IntentDecomposition 결과
    """
    sanitized_query = sanitize_user_query(user_message=user_message)
    inferred_steps = infer_steps_from_query(user_message=sanitized_query)
    steps: list[ExecutionStep] = []
    for step_value in inferred_steps:
        step_enum = _map_step_value(step_value=step_value)
        if step_enum is not None:
            steps.append(step_enum)

    mode, relative, start, end = extract_date_filter_fields(user_message=sanitized_query)
    date_filter = DateFilter(mode=DateFilterMode(mode), relative=relative, start=start, end=end)

    return IntentDecomposition(
        original_query=sanitized_query,
        steps=steps,
        summary_line_target=extract_summary_line_target(user_message=sanitized_query),
        date_filter=date_filter,
        missing_slots=build_missing_slots(steps=[step.value for step in steps], user_message=sanitized_query),
    )


def evaluate_intent_edge_cases(offline_rule_only: bool = False) -> dict[str, Any]:
    """
    경계 케이스 20개를 실행해 의도 분해 품질 지표를 계산한다.

    Returns:
        케이스별 결과와 요약 지표를 포함한 사전
    """
    parser = None if offline_rule_only else get_intent_parser()
    per_case: list[dict[str, Any]] = []
    elapsed_list: list[float] = []
    steps_pass = 0
    summary_pass = 0
    date_pass = 0
    missing_pass = 0
    all_pass = 0

    for case in INTENT_EDGE_CASES:
        start = time.perf_counter()
        if offline_rule_only:
            decomposition = _build_rule_only_decomposition(user_message=case["utterance"])
        else:
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
            "mode": "offline-rule-only" if offline_rule_only else "model-parser",
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


def _build_arg_parser() -> argparse.ArgumentParser:
    """
    CLI 인자 파서를 생성한다.

    Returns:
        초기화된 ArgumentParser
    """
    parser = argparse.ArgumentParser(description="의도 분해 경계 케이스 품질 평가 스크립트")
    parser.add_argument(
        "--min-accuracy-all-fields",
        type=float,
        default=95.0,
        help="전체 필드 동시 일치 최소 정확도(%)",
    )
    parser.add_argument(
        "--max-avg-latency-ms",
        type=float,
        default=2500.0,
        help="허용 가능한 평균 지연(ms) 상한",
    )
    parser.add_argument(
        "--output-json",
        type=str,
        default="",
        help="평가 결과 JSON 저장 경로(옵션)",
    )
    parser.add_argument(
        "--offline-rule-only",
        action="store_true",
        help="모델 호출 없이 규칙 모듈만으로 평가를 수행한다(CI 권장).",
    )
    return parser


def _is_quality_gate_passed(
    result: dict[str, Any],
    min_accuracy_all_fields: float,
    max_avg_latency_ms: float,
) -> bool:
    """
    평가 결과가 품질 게이트 임계치를 통과했는지 판정한다.

    Args:
        result: 평가 결과 사전
        min_accuracy_all_fields: 최소 허용 정확도(%)
        max_avg_latency_ms: 최대 허용 평균 지연(ms)

    Returns:
        통과 시 True, 미통과 시 False
    """
    summary = result.get("summary", {})
    accuracy = float(summary.get("accuracy_all_fields", 0.0))
    avg_latency = float(summary.get("avg_elapsed_ms", 0.0))
    return accuracy >= min_accuracy_all_fields and avg_latency <= max_avg_latency_ms


if __name__ == "__main__":
    # CI/로컬에서 바로 읽기 쉽도록 JSON으로 출력하고 품질 게이트를 판정한다.
    args = _build_arg_parser().parse_args()
    result = evaluate_intent_edge_cases(offline_rule_only=args.offline_rule_only)
    if args.output_json:
        with open(args.output_json, "w", encoding="utf-8") as fp:
            json.dump(result, fp, ensure_ascii=False, indent=2)
    print(json.dumps(result, ensure_ascii=False, indent=2))

    is_passed = _is_quality_gate_passed(
        result=result,
        min_accuracy_all_fields=args.min_accuracy_all_fields,
        max_avg_latency_ms=args.max_avg_latency_ms,
    )
    if is_passed:
        print(
            f"QUALITY_GATE=PASS accuracy_all_fields>={args.min_accuracy_all_fields}, "
            f"avg_elapsed_ms<={args.max_avg_latency_ms}"
        )
    else:
        print(
            f"QUALITY_GATE=FAIL accuracy_all_fields<{args.min_accuracy_all_fields} "
            f"or avg_elapsed_ms>{args.max_avg_latency_ms}"
        )
        raise SystemExit(1)
