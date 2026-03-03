from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.core.chat_eval_cases import CHAT_EVAL_CASES, ChatEvalCase
from app.core.logging_config import get_logger
from app.services.chat_eval_persistence_utils import persist_report
from app.services.chat_eval_service_utils import (
    build_default_judge_caller,
    build_judge_context,
    build_report,
    default_chat_caller,
    resolve_visible_answer,
    rule_based_format_guard,
    rule_based_no_result_judge,
    rule_based_retrieval_grounding_guard,
)

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT_DIR / "data" / "reports"
LATEST_REPORT_PATH = REPORTS_DIR / "chat_eval_latest.json"
DEFAULT_JUDGE_MODEL = "gpt-5-mini"
DEFAULT_CHAT_TIMEOUT_SEC = 90

ChatCaller = Callable[[str, dict[str, Any], int], tuple[int, dict[str, Any], float, str | None]]
JudgeCaller = Callable[[str, str, str, str, dict[str, Any]], tuple[dict[str, Any], float]]


@dataclass(frozen=True)
class CaseRunResult:
    """단일 평가 케이스 실행 결과를 표현한다."""

    case_id: str
    query: str
    expectation: str
    requires_current_mail: bool
    status_code: int
    elapsed_ms: float
    source: str
    answer: str
    error: str | None
    judge: dict[str, Any]
    judge_elapsed_ms: float


def list_chat_eval_cases() -> list[ChatEvalCase]:
    """채팅 평가 케이스 목록을 반환한다."""
    return [dict(case) for case in CHAT_EVAL_CASES]


def run_chat_eval_session(
    *,
    chat_url: str,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    selected_email_id: str = "",
    mailbox_user: str = "",
    request_timeout_sec: int = DEFAULT_CHAT_TIMEOUT_SEC,
    max_cases: int | None = None,
    case_ids: list[str] | None = None,
    chat_caller: ChatCaller | None = None,
    judge_caller: JudgeCaller | None = None,
) -> dict[str, Any]:
    """E2E 채팅 품질 세션을 실행하고 리포트를 저장한다."""
    started_at = datetime.now(tz=timezone.utc)
    active_chat_caller = chat_caller or default_chat_caller
    active_judge_caller = judge_caller or build_default_judge_caller(judge_model=judge_model)
    selected = _select_cases(max_cases=max_cases, case_ids=case_ids)

    logger.info(
        "chat_eval.run.start: cases=%s chat_url=%s judge_model=%s timeout=%s",
        len(selected),
        chat_url,
        judge_model,
        request_timeout_sec,
    )

    case_results: list[CaseRunResult] = []
    for index, case in enumerate(selected, start=1):
        thread_id = f"eval_{int(time.time())}_{index}"
        payload = {"message": case["query"], "thread_id": thread_id}
        if case["requires_current_mail"] and selected_email_id:
            payload["email_id"] = selected_email_id
        if case["requires_current_mail"] and mailbox_user:
            payload["mailbox_user"] = mailbox_user

        status_code, response_json, elapsed_ms, call_error = active_chat_caller(
            chat_url,
            payload,
            request_timeout_sec,
        )
        metadata = response_json.get("metadata", {}) if isinstance(response_json, dict) else {}
        raw_answer = str(response_json.get("answer") or "").strip()
        answer = resolve_visible_answer(raw_answer=raw_answer, metadata=metadata)
        source = str(metadata.get("source") or "")
        judge_context = build_judge_context(metadata=metadata)

        format_override = rule_based_format_guard(query=case["query"], answer=answer)
        no_result_override = rule_based_no_result_judge(
            query=case["query"],
            answer=answer,
            judge_context=judge_context,
        )
        grounding_override = rule_based_retrieval_grounding_guard(
            query=case["query"],
            answer=answer,
            judge_context=judge_context,
        )

        if format_override is not None:
            judge_result, judge_elapsed_ms = format_override, 0.0
        elif no_result_override is not None:
            judge_result, judge_elapsed_ms = no_result_override, 0.0
        elif grounding_override is not None:
            judge_result, judge_elapsed_ms = grounding_override, 0.0
        else:
            judge_result, judge_elapsed_ms = active_judge_caller(
                case["query"],
                answer,
                case["expectation"],
                source,
                judge_context,
            )

        case_results.append(
            CaseRunResult(
                case_id=case["case_id"],
                query=case["query"],
                expectation=case["expectation"],
                requires_current_mail=bool(case["requires_current_mail"]),
                status_code=status_code,
                elapsed_ms=elapsed_ms,
                source=source,
                answer=answer,
                error=call_error,
                judge=judge_result,
                judge_elapsed_ms=judge_elapsed_ms,
            )
        )

    finished_at = datetime.now(tz=timezone.utc)
    report = build_report(
        started_at=started_at,
        finished_at=finished_at,
        chat_url=chat_url,
        judge_model=judge_model,
        selected_email_id=selected_email_id,
        mailbox_user=mailbox_user,
        case_results=case_results,
    )
    persist_report(report=report, reports_dir=REPORTS_DIR, latest_report_path=LATEST_REPORT_PATH)
    logger.info(
        "chat_eval.run.completed: total=%s pass_rate=%.1f avg_chat_ms=%.1f avg_judge_ms=%.1f",
        report["summary"]["total_cases"],
        report["summary"]["judge_pass_rate"],
        report["summary"]["avg_chat_elapsed_ms"],
        report["summary"]["avg_judge_elapsed_ms"],
    )
    return report


def load_latest_chat_eval_report() -> dict[str, Any] | None:
    """최근 저장된 채팅 평가 리포트를 로드한다."""
    if not LATEST_REPORT_PATH.exists():
        return None
    try:
        return json.loads(LATEST_REPORT_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        logger.error("chat_eval.load_latest_failed: %s", exc)
        return None


def _select_cases(max_cases: int | None, case_ids: list[str] | None = None) -> list[ChatEvalCase]:
    """실행할 평가 케이스를 선택한다."""
    cases = list_chat_eval_cases()
    normalized_ids = {
        str(case_id or "").strip() for case_id in (case_ids or []) if str(case_id or "").strip()
    }
    if normalized_ids:
        filtered = [case for case in cases if str(case.get("case_id") or "") in normalized_ids]
    else:
        filtered = cases
    if max_cases is None or max_cases <= 0:
        return filtered
    return filtered[:max_cases]
