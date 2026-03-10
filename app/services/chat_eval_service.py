from __future__ import annotations

import json
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable

from app.core.chat_eval_cases import CHAT_EVAL_CASES, ChatEvalCase
from app.core.intent_rules import is_mail_search_query
from app.core.logging_config import get_logger
from app.services.chat_eval_case_loader import load_chat_eval_cases
from app.services.chat_eval_history_store import record_chat_eval_run
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
_CURRENT_MAIL_HINT_TOKENS: tuple[str, ...] = (
    "현재메일",
    "현재 메일",
    "이 메일",
    "이메일",
    "해당 메일",
    "이 견적",
    "해당 견적",
    "이 프로젝트",
    "해당 프로젝트",
)
_GLOBAL_MAIL_HINT_TOKENS: tuple[str, ...] = (
    "전체메일",
    "전체 메일",
    "메일함 전체",
    "전체 메일함",
    "전체에서",
    "전체 검색",
    "최근 메일",
    "모든 메일",
    "관련 메일",
    "메일 조회",
    "메일 검색",
)

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
    raw_answer: str
    answer: str
    answer_format: dict[str, Any]
    error: str | None
    judge: dict[str, Any]
    judge_elapsed_ms: float
    guard_name: str
    used_current_mail_context: bool
    query_type: str
    resolved_scope: str
    intent_task_type: str
    intent_output_format: str
    intent_confidence: float
    tool_action: str
    server_elapsed_ms: float
    search_result_count: int
    evidence_count: int
    evidence_blank_snippet_count: int
    evidence_top_k: list[dict[str, str]]
    metadata_snapshot: dict[str, Any]


def list_chat_eval_cases(cases_file: str | None = None) -> list[ChatEvalCase]:
    """채팅 평가 케이스 목록을 반환한다.

    외부 파일이 지정되지 않은 기본 경로에서는 모듈 상수 케이스셋을 사용해
    기존 테스트/호출 호환성을 유지한다.
    """
    if not cases_file:
        return [dict(case) for case in CHAT_EVAL_CASES]
    return load_chat_eval_cases(cases_file=cases_file)


def run_chat_eval_session(
    *,
    chat_url: str,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    selected_email_id: str = "",
    mailbox_user: str = "",
    request_timeout_sec: int = DEFAULT_CHAT_TIMEOUT_SEC,
    max_cases: int | None = None,
    case_ids: list[str] | None = None,
    cases_file: str | None = None,
    chat_caller: ChatCaller | None = None,
    judge_caller: JudgeCaller | None = None,
) -> dict[str, Any]:
    """E2E 채팅 품질 세션을 실행하고 리포트를 저장한다."""
    started_at = datetime.now(tz=timezone.utc)
    active_chat_caller = chat_caller or default_chat_caller
    active_judge_caller = judge_caller or build_default_judge_caller(judge_model=judge_model)
    selected = _select_cases(max_cases=max_cases, case_ids=case_ids, cases_file=cases_file)

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
        use_current_mail_context = should_attach_current_mail_context(
            query=str(case["query"] or ""),
            requires_current_mail=bool(case["requires_current_mail"]),
            selected_email_id=selected_email_id,
        )
        if use_current_mail_context and selected_email_id:
            payload["email_id"] = selected_email_id
            payload["runtime_options"] = {"scope": "current_mail"}
        if use_current_mail_context and mailbox_user:
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
        guard_name = ""

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
            guard_name = "format_guard"
        elif no_result_override is not None:
            judge_result, judge_elapsed_ms = no_result_override, 0.0
            guard_name = "no_result_guard"
        elif grounding_override is not None:
            judge_result, judge_elapsed_ms = grounding_override, 0.0
            guard_name = "grounding_guard"
        else:
            judge_result, judge_elapsed_ms = active_judge_caller(
                case["query"],
                answer,
                case["expectation"],
                source,
                judge_context,
            )
            guard_name = "judge_llm"

        evidence_top_k = judge_context.get("evidence_top_k")
        evidence_blank_snippet_count = 0
        if isinstance(evidence_top_k, list):
            evidence_blank_snippet_count = sum(
                1
                for item in evidence_top_k
                if isinstance(item, dict) and not str(item.get("snippet") or "").strip()
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
                raw_answer=raw_answer,
                answer=answer,
                answer_format=metadata.get("answer_format") if isinstance(metadata.get("answer_format"), dict) else {},
                error=call_error,
                judge=judge_result,
                judge_elapsed_ms=judge_elapsed_ms,
                guard_name=guard_name,
                used_current_mail_context=bool(use_current_mail_context),
                query_type=str(metadata.get("query_type") or ""),
                resolved_scope=str(metadata.get("resolved_scope") or ""),
                intent_task_type=str(metadata.get("intent_task_type") or ""),
                intent_output_format=str(metadata.get("intent_output_format") or ""),
                intent_confidence=float(metadata.get("intent_confidence") or 0.0),
                tool_action=str(metadata.get("tool_action") or ""),
                server_elapsed_ms=float(metadata.get("elapsed_ms") or 0.0),
                search_result_count=int(judge_context.get("search_result_count") or 0),
                evidence_count=int(judge_context.get("evidence_count") or 0),
                evidence_blank_snippet_count=int(evidence_blank_snippet_count),
                evidence_top_k=[
                    item
                    for item in (judge_context.get("evidence_top_k") or [])
                    if isinstance(item, dict)
                ],
                metadata_snapshot={
                    "source": source,
                    "query_type": str(metadata.get("query_type") or ""),
                    "resolved_scope": str(metadata.get("resolved_scope") or ""),
                    "intent_task_type": str(metadata.get("intent_task_type") or ""),
                    "intent_output_format": str(metadata.get("intent_output_format") or ""),
                    "intent_confidence": float(metadata.get("intent_confidence") or 0.0),
                    "tool_action": str(metadata.get("tool_action") or ""),
                    "search_result_count": int(judge_context.get("search_result_count") or 0),
                    "evidence_count": int(judge_context.get("evidence_count") or 0),
                    "server_elapsed_ms": float(metadata.get("elapsed_ms") or 0.0),
                    "answer_format": (
                        metadata.get("answer_format")
                        if isinstance(metadata.get("answer_format"), dict)
                        else {}
                    ),
                },
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
    run_no = record_chat_eval_run(report=report)
    report_meta = report.get("meta", {}) if isinstance(report, dict) else {}
    if isinstance(report_meta, dict):
        report_meta["run_no"] = run_no
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


def _select_cases(
    max_cases: int | None,
    case_ids: list[str] | None = None,
    cases_file: str | None = None,
) -> list[ChatEvalCase]:
    """실행할 평가 케이스를 선택한다."""
    cases = list_chat_eval_cases(cases_file=cases_file)
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


def should_attach_current_mail_context(
    *,
    query: str,
    requires_current_mail: bool,
    selected_email_id: str,
) -> bool:
    """
    채팅 평가 요청 payload에 현재메일 컨텍스트를 주입할지 판정한다.

    Args:
        query: 케이스 질의
        requires_current_mail: 케이스 로더가 판정한 현재메일 플래그
        selected_email_id: UI에서 제공된 선택 메일 ID

    Returns:
        현재메일 컨텍스트를 붙여야 하면 True
    """
    if not str(selected_email_id or "").strip():
        return False
    if requires_current_mail:
        return True
    normalized = normalize_query_for_scope(query=query)
    if not normalized:
        return False
    if contains_any_scope_token(text=normalized, tokens=_GLOBAL_MAIL_HINT_TOKENS):
        return False
    if contains_any_scope_token(text=normalized, tokens=_CURRENT_MAIL_HINT_TOKENS):
        return True
    return not is_mail_search_query(normalized)


def normalize_query_for_scope(*, query: str) -> str:
    """
    스코프 판정용 질의를 정규화한다.

    Args:
        query: 원본 질의

    Returns:
        소문자/공백 정규화 문자열
    """
    compact = str(query or "").lower().strip()
    return " ".join(compact.split())


def contains_any_scope_token(*, text: str, tokens: tuple[str, ...]) -> bool:
    """
    텍스트에 지정된 스코프 토큰이 포함되는지 확인한다.

    Args:
        text: 검색 대상 텍스트
        tokens: 토큰 목록

    Returns:
        포함되면 True
    """
    return any(token in text for token in tokens)
