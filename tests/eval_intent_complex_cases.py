from __future__ import annotations

import json
import logging
import time
from statistics import mean
from typing import Any

from app.agents.intent_parser import get_intent_parser
from tests.fixtures.intent_complex_cases import INTENT_COMPLEX_CASES

logger = logging.getLogger(__name__)


def _configure_logging() -> None:
    """평가 스크립트 로깅 포맷을 초기화한다."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )


def _normalize_step_value(step: object) -> str:
    """
    step 값을 비교 가능한 문자열로 정규화한다.

    Args:
        step: ExecutionStep enum 또는 문자열

    Returns:
        정규화된 step 문자열
    """
    if hasattr(step, "value"):
        return str(getattr(step, "value"))
    text = str(step or "")
    if text.startswith("ExecutionStep."):
        return text.split(".", 1)[1].lower()
    return text.strip()


def evaluate_intent_complex_cases() -> dict[str, Any]:
    """
    복합질의 20개를 실행해 구조분해 품질과 지연을 측정한다.

    Returns:
        요약 지표 및 케이스별 결과 사전
    """
    parser = get_intent_parser()
    cases: list[dict[str, Any]] = []
    elapsed_values: list[float] = []
    parse_success_count = 0
    required_steps_pass_count = 0

    for case in INTENT_COMPLEX_CASES:
        started = time.perf_counter()
        decomposition = parser.parse(case["utterance"])
        elapsed_ms = round((time.perf_counter() - started) * 1000, 1)
        elapsed_values.append(elapsed_ms)

        actual = decomposition.model_dump()
        actual_steps = [_normalize_step_value(step=step) for step in actual.get("steps", [])]
        required_steps = list(case["required_steps"])
        required_ok = all(step in actual_steps for step in required_steps)
        parse_ok = bool(actual_steps)

        parse_success_count += int(parse_ok)
        required_steps_pass_count += int(required_ok)

        cases.append(
            {
                "case_id": case["case_id"],
                "pattern": case["pattern"],
                "utterance": case["utterance"],
                "elapsed_ms": elapsed_ms,
                "parse_success": parse_ok,
                "required_steps_ok": required_ok,
                "actual_steps": actual_steps,
                "required_steps": required_steps,
                "summary_line_target": actual.get("summary_line_target", 0),
                "date_filter": actual.get("date_filter", {}),
                "missing_slots": actual.get("missing_slots", []),
            }
        )

    total = len(INTENT_COMPLEX_CASES)
    return {
        "summary": {
            "total": total,
            "parse_success_count": parse_success_count,
            "parse_success_rate": round((parse_success_count / total) * 100, 1),
            "required_steps_pass_count": required_steps_pass_count,
            "required_steps_pass_rate": round((required_steps_pass_count / total) * 100, 1),
            "avg_elapsed_ms": round(mean(elapsed_values), 1),
            "max_elapsed_ms": max(elapsed_values),
            "min_elapsed_ms": min(elapsed_values),
        },
        "cases": cases,
    }


def _write_result(path: str, result: dict[str, Any]) -> None:
    """
    평가 결과를 JSON 파일로 저장한다.

    Args:
        path: 출력 파일 경로
        result: 평가 결과 사전
    """
    with open(path, "w", encoding="utf-8") as file:
        json.dump(result, file, ensure_ascii=False, indent=2)


if __name__ == "__main__":
    _configure_logging()
    output_path = "tests/intent_complex_eval_result.json"
    evaluation = evaluate_intent_complex_cases()
    _write_result(path=output_path, result=evaluation)
    logger.info("복합질의 평가 완료: %s", json.dumps(evaluation["summary"], ensure_ascii=False))
    logger.info("복합질의 평가 상세 결과 저장: %s", output_path)
