from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from app.core.logging_config import get_logger
from app.services.chat_eval_pipeline_service import run_chat_eval_pipeline

logger = get_logger(__name__)


def parse_args(argv: list[str]) -> argparse.Namespace:
    """
    CLI 인자를 파싱한다.

    Args:
        argv: 원본 argv

    Returns:
        파싱된 네임스페이스
    """
    parser = argparse.ArgumentParser(description="Run chat-eval pipeline (run+compare+gate).")
    parser.add_argument("--chat-url", required=True, help="Target /search/chat URL")
    parser.add_argument("--judge-model", default="gpt-5-mini")
    parser.add_argument("--max-cases", type=int, default=0)
    parser.add_argument("--case-ids", default="", help="Comma-separated case ids")
    parser.add_argument("--cases-file", default="", help="External cases file path (.md/.json)")
    parser.add_argument("--selected-email-id", default="")
    parser.add_argument("--mailbox-user", default="")
    parser.add_argument("--request-timeout-sec", type=int, default=90)
    parser.add_argument("--min-pass-rate", type=float, default=85.0)
    parser.add_argument("--min-avg-score", type=float, default=3.5)
    parser.add_argument("--allow-regression-cases", type=int, default=0)
    return parser.parse_args(argv)


def _parse_case_ids(raw_value: str) -> list[str]:
    """
    case_ids 문자열을 리스트로 변환한다.

    Args:
        raw_value: comma-separated 문자열

    Returns:
        정규화된 case id 목록
    """
    values = [item.strip() for item in str(raw_value or "").split(",")]
    return [item for item in values if item]


def main(argv: list[str]) -> int:
    """
    파이프라인 실행 진입점.

    Args:
        argv: CLI 인자 목록

    Returns:
        종료 코드(0=성공, 1=실패)
    """
    args = parse_args(argv=argv)
    case_ids = _parse_case_ids(raw_value=args.case_ids)
    report = run_chat_eval_pipeline(
        chat_url=str(args.chat_url).strip(),
        judge_model=str(args.judge_model).strip(),
        selected_email_id=str(args.selected_email_id).strip(),
        mailbox_user=str(args.mailbox_user).strip(),
        request_timeout_sec=max(10, int(args.request_timeout_sec)),
        max_cases=(int(args.max_cases) if int(args.max_cases) > 0 else None),
        case_ids=case_ids or None,
        cases_file=str(args.cases_file).strip() or None,
        min_pass_rate=float(args.min_pass_rate),
        min_avg_score=float(args.min_avg_score),
        allow_regression_cases=max(0, int(args.allow_regression_cases)),
    )
    gate = report.get("quality_gate", {}) if isinstance(report, dict) else {}
    logger.info(
        "chat_eval.pipeline.cli.result: passed=%s failed_checks=%s",
        bool(gate.get("passed")),
        ",".join([str(item) for item in gate.get("failed_checks", [])]) if isinstance(gate.get("failed_checks"), list) else "",
    )
    logger.info("chat_eval.pipeline.cli.report: %s", json.dumps(report.get("quality_gate", {}), ensure_ascii=False))
    return 0 if bool(gate.get("passed")) else 1


if __name__ == "__main__":
    sys.exit(main(argv=sys.argv[1:]))
