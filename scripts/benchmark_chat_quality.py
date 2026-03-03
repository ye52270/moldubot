from __future__ import annotations

import argparse
import json
from typing import Any

from app.services.chat_quality_benchmark import aggregate_benchmark_runs
from tests.eval_chat_quality_cases import DEFAULT_CHAT_URL, run_chat_quality_cases


def run_benchmark(
    chat_url: str,
    warmup_runs: int,
    measure_runs: int,
    top_n: int,
    request_timeout_sec: int,
    max_cases: int | None,
) -> dict[str, Any]:
    """
    채팅 품질 케이스를 반복 실행해 성능 지표를 집계한다.

    Args:
        chat_url: `/search/chat` 엔드포인트 URL
        warmup_runs: 워밍업 반복 횟수
        measure_runs: 본측정 반복 횟수
        top_n: 느린 케이스 상위 개수
        request_timeout_sec: 케이스별 HTTP 타임아웃(초)
        max_cases: 실행할 최대 케이스 수

    Returns:
        반복 실행 원본/집계 결과
    """
    for _ in range(max(0, warmup_runs)):
        run_chat_quality_cases(
            chat_url=chat_url,
            request_timeout_sec=request_timeout_sec,
            max_cases=max_cases,
        )
    measured_runs = [
        run_chat_quality_cases(
            chat_url=chat_url,
            request_timeout_sec=request_timeout_sec,
            max_cases=max_cases,
        )
        for _ in range(max(1, measure_runs))
    ]
    aggregate = aggregate_benchmark_runs(measured_runs=measured_runs, top_n=top_n)
    return {
        "chat_url": chat_url,
        "warmup_runs": max(0, warmup_runs),
        "measure_runs": max(1, measure_runs),
        "request_timeout_sec": max(1, int(request_timeout_sec)),
        "max_cases": int(max_cases) if isinstance(max_cases, int) and max_cases > 0 else None,
        "aggregate": aggregate,
        "runs": measured_runs,
    }


def parse_args() -> argparse.Namespace:
    """
    커맨드라인 인자를 파싱한다.

    Returns:
        파싱된 인자 객체
    """
    parser = argparse.ArgumentParser(description="Benchmark /search/chat with quality cases")
    parser.add_argument("--chat-url", default=DEFAULT_CHAT_URL, help="Target /search/chat URL")
    parser.add_argument("--warmup-runs", type=int, default=1, help="Warmup run count")
    parser.add_argument("--measure-runs", type=int, default=3, help="Measured run count")
    parser.add_argument("--top-n", type=int, default=3, help="Top slow case count")
    parser.add_argument("--request-timeout-sec", type=int, default=45, help="Per case request timeout seconds")
    parser.add_argument("--max-cases", type=int, default=0, help="Max cases per run (0 means all)")
    return parser.parse_args()


def main() -> None:
    """
    벤치마크를 실행하고 JSON 결과를 출력한다.
    """
    args = parse_args()
    result = run_benchmark(
        chat_url=str(args.chat_url),
        warmup_runs=int(args.warmup_runs),
        measure_runs=int(args.measure_runs),
        top_n=int(args.top_n),
        request_timeout_sec=int(args.request_timeout_sec),
        max_cases=int(args.max_cases) if int(args.max_cases) > 0 else None,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
