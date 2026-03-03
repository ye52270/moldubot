from __future__ import annotations

from statistics import mean
from typing import Any


def aggregate_benchmark_runs(
    measured_runs: list[dict[str, Any]],
    top_n: int = 3,
) -> dict[str, Any]:
    """
    채팅 품질 반복 측정 결과를 집계한다.

    Args:
        measured_runs: `run_chat_quality_cases` 결과 배열
        top_n: 느린 케이스 상위 개수

    Returns:
        평균/최대/최소 지연과 케이스별 상위 지연 정보를 포함한 집계 결과
    """
    if not measured_runs:
        return {
            "run_count": 0,
            "avg_elapsed_ms_mean": 0.0,
            "avg_elapsed_ms_min": 0.0,
            "avg_elapsed_ms_max": 0.0,
            "p95_case_elapsed_ms": 0.0,
            "top_slow_cases": [],
        }

    avg_elapsed_values = [
        float(run.get("summary", {}).get("avg_elapsed_ms") or 0.0)
        for run in measured_runs
    ]
    all_case_elapsed_values = _collect_case_elapsed_values(measured_runs=measured_runs)
    per_case = build_per_case_stats(measured_runs=measured_runs)
    sorted_cases = sorted(
        per_case,
        key=lambda item: (float(item.get("avg_elapsed_ms") or 0.0), float(item.get("max_elapsed_ms") or 0.0)),
        reverse=True,
    )
    return {
        "run_count": len(measured_runs),
        "avg_elapsed_ms_mean": round(mean(avg_elapsed_values), 1),
        "avg_elapsed_ms_min": round(min(avg_elapsed_values), 1),
        "avg_elapsed_ms_max": round(max(avg_elapsed_values), 1),
        "p95_case_elapsed_ms": percentile(values=all_case_elapsed_values, percent=95),
        "top_slow_cases": sorted_cases[: max(1, int(top_n or 3))],
    }


def build_per_case_stats(measured_runs: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """
    반복 측정 결과에서 케이스별 지연 통계를 계산한다.

    Args:
        measured_runs: `run_chat_quality_cases` 결과 배열

    Returns:
        케이스별 평균/최대 지연 통계
    """
    grouped: dict[str, dict[str, Any]] = {}
    for run in measured_runs:
        cases = run.get("cases")
        if not isinstance(cases, list):
            continue
        for case in cases:
            if not isinstance(case, dict):
                continue
            case_id = str(case.get("case_id") or "").strip()
            if not case_id:
                continue
            elapsed = float(case.get("elapsed_ms") or 0.0)
            bucket = grouped.setdefault(
                case_id,
                {
                    "case_id": case_id,
                    "pattern": str(case.get("pattern") or "").strip(),
                    "utterance": str(case.get("utterance") or "").strip(),
                    "elapsed_samples": [],
                },
            )
            samples = bucket.get("elapsed_samples")
            if isinstance(samples, list):
                samples.append(elapsed)

    result: list[dict[str, Any]] = []
    for row in grouped.values():
        samples = row.get("elapsed_samples")
        if not isinstance(samples, list) or not samples:
            continue
        result.append(
            {
                "case_id": row["case_id"],
                "pattern": row["pattern"],
                "utterance": row["utterance"],
                "avg_elapsed_ms": round(mean(samples), 1),
                "max_elapsed_ms": round(max(samples), 1),
                "min_elapsed_ms": round(min(samples), 1),
                "sample_count": len(samples),
            }
        )
    return result


def percentile(values: list[float], percent: int) -> float:
    """
    실수 리스트의 분위수를 계산한다.

    Args:
        values: 입력 값 배열
        percent: 분위수(0~100)

    Returns:
        계산된 분위수 값
    """
    if not values:
        return 0.0
    sorted_values = sorted(float(item) for item in values)
    index = int((len(sorted_values) - 1) * (max(0, min(percent, 100)) / 100))
    return round(sorted_values[index], 1)


def _collect_case_elapsed_values(measured_runs: list[dict[str, Any]]) -> list[float]:
    """
    반복 측정 결과에서 케이스 지연값을 평탄화한다.

    Args:
        measured_runs: `run_chat_quality_cases` 결과 배열

    Returns:
        케이스 지연값 배열
    """
    elapsed_values: list[float] = []
    for run in measured_runs:
        cases = run.get("cases")
        if not isinstance(cases, list):
            continue
        for case in cases:
            if not isinstance(case, dict):
                continue
            elapsed_values.append(float(case.get("elapsed_ms") or 0.0))
    return elapsed_values
