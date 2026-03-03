from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, HTTPException

from app.api.contracts import FinanceClaimRequest, HrRequest, PromiseDraftRequest
from app.api.data_access import (
    FINANCE_CLAIMS_PATH,
    MYHR_REQUESTS_PATH,
    PROMISE_DRAFTS_PATH,
    append_json_list,
    finance_projects as load_finance_projects,
    promise_costs as load_promise_costs,
    promise_projects as load_promise_projects,
    read_json,
)

router = APIRouter()


@router.get("/api/promise/projects")
def promise_projects() -> dict[str, Any]:
    """
    Promise 프로젝트 목록을 반환한다.

    Returns:
        프로젝트 목록과 건수
    """
    projects = load_promise_projects()
    return {"projects": projects, "count": len(projects)}


@router.get("/api/promise/summaries")
def promise_summaries() -> dict[str, Any]:
    """
    legacy Promise 조회 목록(프로젝트 + 실행예산 합계)을 반환한다.

    Returns:
        실행예산 조회 목록과 건수
    """
    project_rows = load_promise_projects()
    project_name_by_number = {
        str(item.get("project_number") or "").strip(): str(item.get("project_name") or "").strip()
        for item in project_rows
        if isinstance(item, dict)
    }
    summaries: list[dict[str, Any]] = []
    for item in load_promise_costs():
        if not isinstance(item, dict):
            continue
        project_number = str(item.get("project_number") or "").strip()
        if not project_number:
            continue
        summaries.append(
            {
                "project_number": project_number,
                "project_name": project_name_by_number.get(project_number, ""),
                "execution_total": int(item.get("execution_total") or 0),
                "final_cost_total": int(item.get("final_cost_total") or 0),
            }
        )
    return {"items": summaries, "count": len(summaries)}


@router.get("/api/promise/projects/{project_number}/summary")
def promise_project_summary(project_number: str) -> dict[str, Any]:
    """
    프로젝트 번호 기준 Promise 요약을 반환한다.

    Args:
        project_number: 프로젝트 번호

    Returns:
        프로젝트 요약 객체
    """
    target = str(project_number or "").strip()
    for item in load_promise_costs():
        if str(item.get("project_number", "")).strip() == target:
            return item
    raise HTTPException(status_code=404, detail="프로젝트 요약을 찾지 못했습니다.")


@router.get("/api/promise/drafts")
def promise_drafts() -> dict[str, Any]:
    """
    저장된 실행예산 draft 목록을 반환한다.

    Returns:
        최신순 draft 목록과 건수
    """
    rows = read_json(PROMISE_DRAFTS_PATH, [])
    drafts = rows if isinstance(rows, list) else []
    normalized: list[dict[str, Any]] = []
    for item in drafts:
        if not isinstance(item, dict):
            continue
        normalized.append(
            {
                "saved_at": str(item.get("saved_at") or "").strip(),
                "project_number": str(item.get("project_number") or "").strip(),
                "project_name": str(item.get("project_name") or "").strip(),
                "mode": str(item.get("mode") or "").strip(),
                "final_cost_total": int(item.get("final_cost_total") or 0),
                "reason": str(item.get("reason") or "").strip(),
                "thread_id": str(item.get("thread_id") or "").strip(),
            }
        )
    normalized.sort(key=lambda row: row.get("saved_at", ""), reverse=True)
    return {"drafts": normalized, "count": len(normalized)}


@router.get("/api/finance/projects")
def finance_projects() -> dict[str, Any]:
    """
    비용정산 프로젝트 목록을 반환한다.

    Returns:
        프로젝트 목록과 건수
    """
    projects = load_finance_projects()
    return {"projects": projects, "count": len(projects)}


@router.get("/api/finance/projects/{project_number}/budget")
def finance_project_budget(project_number: str) -> dict[str, Any]:
    """
    프로젝트 번호 기준 비용정산 예산 정보를 반환한다.

    Args:
        project_number: 프로젝트 번호

    Returns:
        예산 상세 객체
    """
    project = _find_finance_project(project_number=project_number)
    if project is not None:
        return project
    raise HTTPException(status_code=404, detail="비용정산 예산 정보를 찾지 못했습니다.")


@router.post("/api/promise/drafts")
def save_promise_draft(payload: PromiseDraftRequest) -> dict[str, Any]:
    """
    실행예산 draft를 mock 저장소에 저장한다.

    Args:
        payload: 실행예산 draft 요청

    Returns:
        저장 결과
    """
    project_number = str(payload.project_number or "").strip()
    if not project_number:
        return {"status": "failed", "reason": "project_number는 필수입니다."}
    record = {
        "saved_at": datetime.now(tz=timezone.utc).isoformat(),
        "project_number": project_number,
        "project_name": str(payload.project_name or "").strip(),
        "mode": str(payload.mode or "create").strip() or "create",
        "final_cost_total": max(0, int(payload.final_cost_total or 0)),
        "reason": str(payload.reason or "").strip(),
        "thread_id": str(payload.thread_id or "").strip(),
    }
    append_json_list(PROMISE_DRAFTS_PATH, record)
    return {"status": "completed", "draft": record}


@router.post("/api/finance/claims")
def save_finance_claim(payload: FinanceClaimRequest) -> dict[str, Any]:
    """
    비용정산 claim을 mock 저장소에 저장하고 예산 요약을 반환한다.

    Args:
        payload: 비용정산 요청

    Returns:
        저장 결과 + 예산 정보
    """
    project_number = str(payload.project_number or "").strip()
    amount = max(0, int(payload.amount or 0))
    if not project_number:
        return {"status": "failed", "reason": "project_number는 필수입니다."}
    if amount <= 0:
        return {"status": "failed", "reason": "amount는 1원 이상이어야 합니다."}

    project = _find_finance_project(project_number=project_number)
    if project is None:
        return {"status": "failed", "reason": "대상 프로젝트를 찾지 못했습니다."}

    remaining = int(project.get("remaining_amount") or 0)
    if amount > remaining:
        return {"status": "failed", "reason": "요청 금액이 잔여 예산을 초과했습니다."}

    record = {
        "saved_at": datetime.now(tz=timezone.utc).isoformat(),
        "project_number": project_number,
        "expense_category": str(payload.expense_category or "").strip(),
        "amount": amount,
        "description": str(payload.description or "").strip(),
        "evidence_files": [str(name).strip() for name in payload.evidence_files if str(name or "").strip()],
        "thread_id": str(payload.thread_id or "").strip(),
    }
    append_json_list(FINANCE_CLAIMS_PATH, record)
    budget = {
        "expense_budget_total": int(project.get("expense_budget_total") or 0),
        "used_amount": int(project.get("used_amount") or 0) + amount,
        "remaining_amount": max(0, remaining - amount),
    }
    return {"status": "completed", "claim": record, "budget": budget}


@router.post("/api/myhr/requests")
def save_myhr_request(payload: HrRequest) -> dict[str, Any]:
    """
    근태/휴가 신청 요청을 mock 저장소에 저장한다.

    Args:
        payload: 근태 요청

    Returns:
        저장 결과
    """
    request_type = str(payload.request_type or "").strip()
    request_date = str(payload.request_date or "").strip()
    if not request_type:
        return {"status": "failed", "reason": "request_type은 필수입니다."}
    if not request_date:
        return {"status": "failed", "reason": "request_date는 필수입니다."}
    record = {
        "saved_at": datetime.now(tz=timezone.utc).isoformat(),
        "request_type": request_type,
        "request_date": request_date,
        "reason": str(payload.reason or "").strip(),
        "thread_id": str(payload.thread_id or "").strip(),
    }
    append_json_list(MYHR_REQUESTS_PATH, record)
    return {"status": "completed", "request": record}


def _find_finance_project(project_number: str) -> dict[str, Any] | None:
    """
    프로젝트 번호로 비용정산 대상 프로젝트를 조회한다.

    Args:
        project_number: 프로젝트 번호

    Returns:
        프로젝트 사전 또는 None
    """
    target = str(project_number or "").strip()
    if not target:
        return None
    for item in load_finance_projects():
        if str(item.get("project_number", "")).strip() == target:
            return item
    return None
