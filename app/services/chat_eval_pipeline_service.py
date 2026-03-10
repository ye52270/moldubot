from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging_config import get_logger
from app.services.chat_eval_persistence_utils import sanitize_timestamp
from app.services.chat_eval_service import (
    DEFAULT_JUDGE_MODEL,
    load_latest_chat_eval_report,
    run_chat_eval_session,
)

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
REPORTS_DIR = ROOT_DIR / "data" / "reports"
PIPELINE_LATEST_PATH = REPORTS_DIR / "chat_eval_pipeline_latest.json"
PIPELINE_HISTORY_PATH = REPORTS_DIR / "chat_eval_pipeline_history.ndjson"


def run_chat_eval_pipeline(
    *,
    chat_url: str,
    judge_model: str = DEFAULT_JUDGE_MODEL,
    selected_email_id: str = "",
    mailbox_user: str = "",
    request_timeout_sec: int = 90,
    max_cases: int | None = None,
    case_ids: list[str] | None = None,
    cases_file: str | None = None,
    min_pass_rate: float = 85.0,
    min_avg_score: float = 3.5,
    allow_regression_cases: int = 0,
) -> dict[str, Any]:
    """
    Chat E2E 평가를 실행하고 baseline 대비 회귀 분석/품질 게이트 결과를 생성한다.

    Args:
        chat_url: `/search/chat` URL
        judge_model: Judge 모델명
        selected_email_id: 현재메일 케이스용 메일 ID
        mailbox_user: 현재메일 케이스용 mailbox user
        request_timeout_sec: 단일 케이스 타임아웃(초)
        max_cases: 최대 실행 케이스 수
        case_ids: 실행할 케이스 ID 목록
        min_pass_rate: 게이트 최소 통과율(%)
        min_avg_score: 게이트 최소 평균 점수
        allow_regression_cases: 허용 회귀 케이스 수

    Returns:
        파이프라인 결과 dict
    """
    baseline_report = load_latest_chat_eval_report()
    current_report = run_chat_eval_session(
        chat_url=chat_url,
        judge_model=judge_model,
        selected_email_id=selected_email_id,
        mailbox_user=mailbox_user,
        request_timeout_sec=request_timeout_sec,
        max_cases=max_cases,
        case_ids=case_ids,
        cases_file=cases_file,
    )
    comparison = compare_chat_eval_reports(
        baseline_report=baseline_report,
        current_report=current_report,
    )
    gate = evaluate_quality_gate(
        report=current_report,
        comparison=comparison,
        min_pass_rate=min_pass_rate,
        min_avg_score=min_avg_score,
        allow_regression_cases=allow_regression_cases,
    )
    pipeline_report = build_pipeline_report(
        current_report=current_report,
        comparison=comparison,
        quality_gate=gate,
        config={
            "chat_url": chat_url,
            "judge_model": judge_model,
            "request_timeout_sec": int(request_timeout_sec),
            "max_cases": max_cases,
            "case_ids": list(case_ids or []),
            "cases_file": str(cases_file or ""),
            "selected_email_id_provided": bool(selected_email_id),
            "mailbox_user_provided": bool(mailbox_user),
            "min_pass_rate": float(min_pass_rate),
            "min_avg_score": float(min_avg_score),
            "allow_regression_cases": int(allow_regression_cases),
        },
    )
    persist_pipeline_report(report=pipeline_report)
    logger.info(
        "chat_eval.pipeline.completed: passed=%s pass_rate=%.1f avg_score=%.2f regressions=%s",
        gate.get("passed"),
        float(current_report.get("summary", {}).get("judge_pass_rate", 0.0)),
        float(current_report.get("summary", {}).get("avg_judge_score", 0.0)),
        int(comparison.get("regression_count", 0)),
    )
    return pipeline_report


def compare_chat_eval_reports(
    baseline_report: dict[str, Any] | None,
    current_report: dict[str, Any],
) -> dict[str, Any]:
    """
    baseline/current 채팅 평가 리포트를 비교해 회귀/개선 케이스를 계산한다.

    Args:
        baseline_report: 이전 리포트(없으면 None)
        current_report: 현재 실행 리포트

    Returns:
        비교 결과 dict
    """
    baseline_cases = _index_case_pass_map(report=baseline_report or {})
    current_cases = _index_case_pass_map(report=current_report)
    regressions: list[str] = []
    improvements: list[str] = []
    stable_failures: list[str] = []
    for case_id, current_pass in current_cases.items():
        previous_pass = baseline_cases.get(case_id)
        if previous_pass is None:
            continue
        if previous_pass and not current_pass:
            regressions.append(case_id)
            continue
        if (not previous_pass) and current_pass:
            improvements.append(case_id)
            continue
        if (not previous_pass) and (not current_pass):
            stable_failures.append(case_id)
    baseline_pass_rate = float((baseline_report or {}).get("summary", {}).get("judge_pass_rate", 0.0))
    current_pass_rate = float(current_report.get("summary", {}).get("judge_pass_rate", 0.0))
    baseline_avg_score = float((baseline_report or {}).get("summary", {}).get("avg_judge_score", 0.0))
    current_avg_score = float(current_report.get("summary", {}).get("avg_judge_score", 0.0))
    return {
        "has_baseline": bool(baseline_report),
        "baseline_total_cases": len(baseline_cases),
        "current_total_cases": len(current_cases),
        "baseline_pass_rate": baseline_pass_rate,
        "current_pass_rate": current_pass_rate,
        "delta_pass_rate": round(current_pass_rate - baseline_pass_rate, 2),
        "baseline_avg_score": baseline_avg_score,
        "current_avg_score": current_avg_score,
        "delta_avg_score": round(current_avg_score - baseline_avg_score, 2),
        "regression_cases": sorted(regressions),
        "improved_cases": sorted(improvements),
        "stable_failure_cases": sorted(stable_failures),
        "regression_count": len(regressions),
    }


def evaluate_quality_gate(
    *,
    report: dict[str, Any],
    comparison: dict[str, Any],
    min_pass_rate: float,
    min_avg_score: float,
    allow_regression_cases: int,
) -> dict[str, Any]:
    """
    품질 게이트 기준(pass_rate/avg_score/regression)을 평가한다.

    Args:
        report: 현재 실행 리포트
        comparison: baseline 비교 결과
        min_pass_rate: 최소 통과율
        min_avg_score: 최소 평균 점수
        allow_regression_cases: 허용 회귀 케이스 수

    Returns:
        게이트 결과 dict
    """
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    pass_rate = float(summary.get("judge_pass_rate", 0.0))
    avg_score = float(summary.get("avg_judge_score", 0.0))
    regression_count = int(comparison.get("regression_count", 0))
    checks = {
        "pass_rate_ok": pass_rate >= float(min_pass_rate),
        "avg_score_ok": avg_score >= float(min_avg_score),
        "regression_ok": regression_count <= int(allow_regression_cases),
    }
    failed_checks = [key for key, ok in checks.items() if not ok]
    return {
        "passed": len(failed_checks) == 0,
        "checks": checks,
        "failed_checks": failed_checks,
        "thresholds": {
            "min_pass_rate": float(min_pass_rate),
            "min_avg_score": float(min_avg_score),
            "allow_regression_cases": int(allow_regression_cases),
        },
        "observed": {
            "pass_rate": pass_rate,
            "avg_score": avg_score,
            "regression_count": regression_count,
        },
    }


def build_pipeline_report(
    *,
    current_report: dict[str, Any],
    comparison: dict[str, Any],
    quality_gate: dict[str, Any],
    config: dict[str, Any],
) -> dict[str, Any]:
    """
    파이프라인 실행 리포트를 생성한다.

    Args:
        current_report: 현재 실행 리포트
        comparison: baseline 비교 결과
        quality_gate: 게이트 평가 결과
        config: 실행 구성값

    Returns:
        파이프라인 리포트 dict
    """
    generated_at = datetime.now(tz=timezone.utc).isoformat()
    return {
        "meta": {
            "generated_at": generated_at,
            "pipeline_version": "v1",
        },
        "config": config,
        "quality_gate": quality_gate,
        "comparison": comparison,
        "report": current_report,
        "action_items": _build_action_items(
            quality_gate=quality_gate,
            comparison=comparison,
            report=current_report,
        ),
    }


def persist_pipeline_report(report: dict[str, Any]) -> None:
    """
    파이프라인 리포트를 latest/타임스탬프/히스토리로 저장한다.

    Args:
        report: 저장할 파이프라인 리포트
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    stamp = sanitize_timestamp(started_at=str(report.get("meta", {}).get("generated_at") or ""))
    stamped_path = REPORTS_DIR / f"chat_eval_pipeline_{stamp}.json"
    body = json.dumps(report, ensure_ascii=False, indent=2)
    PIPELINE_LATEST_PATH.write_text(body, encoding="utf-8")
    stamped_path.write_text(body, encoding="utf-8")
    history_line = json.dumps(
        {
            "generated_at": str(report.get("meta", {}).get("generated_at") or ""),
            "gate_passed": bool(report.get("quality_gate", {}).get("passed")),
            "pass_rate": float(report.get("report", {}).get("summary", {}).get("judge_pass_rate", 0.0)),
            "avg_score": float(report.get("report", {}).get("summary", {}).get("avg_judge_score", 0.0)),
            "regression_count": int(report.get("comparison", {}).get("regression_count", 0)),
        },
        ensure_ascii=False,
    )
    with PIPELINE_HISTORY_PATH.open("a", encoding="utf-8") as fp:
        fp.write(history_line + "\n")


def load_latest_chat_eval_pipeline_report() -> dict[str, Any] | None:
    """
    최근 저장된 파이프라인 리포트를 로드한다.

    Returns:
        리포트 dict 또는 None
    """
    if not PIPELINE_LATEST_PATH.exists():
        return None
    try:
        return json.loads(PIPELINE_LATEST_PATH.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return None


def render_pipeline_report_markdown(report: dict[str, Any]) -> str:
    """
    파이프라인 리포트를 Markdown 요약으로 렌더링한다.

    Args:
        report: 파이프라인 리포트

    Returns:
        Markdown 문자열
    """
    gate = report.get("quality_gate", {}) if isinstance(report, dict) else {}
    comparison = report.get("comparison", {}) if isinstance(report, dict) else {}
    summary = report.get("report", {}).get("summary", {}) if isinstance(report, dict) else {}
    lines = [
        "# Chat Eval Pipeline Report",
        "",
        f"- generated_at: {str(report.get('meta', {}).get('generated_at') or '-')}",
        f"- gate_passed: {bool(gate.get('passed'))}",
        f"- pass_rate: {float(summary.get('judge_pass_rate', 0.0))}",
        f"- avg_score: {float(summary.get('avg_judge_score', 0.0))}",
        f"- regression_count: {int(comparison.get('regression_count', 0))}",
        "",
        "## Failed Checks",
    ]
    failed_checks = gate.get("failed_checks")
    if isinstance(failed_checks, list) and failed_checks:
        for check in failed_checks:
            lines.append(f"- {str(check)}")
    else:
        lines.append("- none")
    lines.append("")
    lines.append("## Regression Cases")
    regressions = comparison.get("regression_cases")
    if isinstance(regressions, list) and regressions:
        for case_id in regressions:
            lines.append(f"- {str(case_id)}")
    else:
        lines.append("- none")
    return "\n".join(lines).strip()


def _index_case_pass_map(report: dict[str, Any]) -> dict[str, bool]:
    """
    리포트 cases를 `case_id -> pass 여부` 맵으로 변환한다.

    Args:
        report: chat eval report

    Returns:
        case pass 맵
    """
    cases = report.get("cases")
    if not isinstance(cases, list):
        return {}
    indexed: dict[str, bool] = {}
    for row in cases:
        if not isinstance(row, dict):
            continue
        case_id = str(row.get("case_id") or "").strip()
        if not case_id:
            continue
        judge = row.get("judge")
        passed = bool(judge.get("pass")) if isinstance(judge, dict) else False
        indexed[case_id] = passed
    return indexed


def _build_action_items(
    *,
    quality_gate: dict[str, Any],
    comparison: dict[str, Any],
    report: dict[str, Any],
) -> list[str]:
    """
    게이트/비교 결과를 기반으로 후속 액션 아이템을 생성한다.

    Args:
        quality_gate: 게이트 결과
        comparison: baseline 비교 결과
        report: 현재 리포트

    Returns:
        액션 아이템 문자열 목록
    """
    actions: list[str] = []
    failed_checks = quality_gate.get("failed_checks")
    if isinstance(failed_checks, list):
        for check in failed_checks:
            if check == "pass_rate_ok":
                actions.append("pass_rate 미달: 실패 케이스 reason 상위 5개를 우선 수정")
            elif check == "avg_score_ok":
                actions.append("avg_score 미달: format/grounded 불일치 케이스를 우선 개선")
            elif check == "regression_ok":
                actions.append("회귀 발생: regression 케이스를 릴리즈 블로커로 처리")
    regressions = comparison.get("regression_cases")
    if isinstance(regressions, list) and regressions:
        actions.append("회귀 케이스: " + ", ".join([str(item) for item in regressions[:8]]))
    if not actions:
        actions.append("품질 게이트 통과: 현재 기준을 baseline으로 승격 검토")
    summary = report.get("summary")
    if isinstance(summary, dict) and int(summary.get("total_cases", 0)) < 10:
        actions.append("케이스 수가 적음: 최소 10~20개 시나리오 유지 권장")
    return actions
