from __future__ import annotations

import json
import os
from pathlib import Path
from typing import Any

from fastapi import Request
from app.services.meeting_room_catalog import load_meeting_rooms

ROOT_DIR = Path(__file__).resolve().parents[2]
PROMISE_PROJECTS_PATH = ROOT_DIR / "clients" / "portals" / "myPromise" / "projects.json"
PROMISE_COSTS_PATH = ROOT_DIR / "clients" / "portals" / "myPromise" / "project_costs.json"
MEETING_ROOMS_PATH = ROOT_DIR / "data" / "meeting" / "meeting_rooms.json"
CLIENT_LOG_PATH = ROOT_DIR / "data" / "mock" / "client_logs.ndjson"
PROMISE_DRAFTS_PATH = ROOT_DIR / "data" / "mock" / "promise_drafts.json"
FINANCE_CLAIMS_PATH = ROOT_DIR / "data" / "mock" / "finance_claims.json"
MYHR_REQUESTS_PATH = ROOT_DIR / "data" / "mock" / "myhr_requests.json"
ADDIN_MANIFEST_PATH = ROOT_DIR / "clients" / "outlook-addin" / "manifest.xml"


def read_json(path: Path, default: Any) -> Any:
    """
    JSON 파일을 읽어 파이썬 객체로 반환한다.

    Args:
        path: 대상 파일 경로
        default: 파일이 없거나 파싱 실패 시 반환할 기본값

    Returns:
        파싱 결과 객체 또는 기본값
    """
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return default


def write_ndjson(path: Path, payload: dict[str, Any]) -> None:
    """
    NDJSON 파일 끝에 단일 레코드를 추가한다.

    Args:
        path: 대상 파일 경로
        payload: 저장할 레코드 사전
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def append_json_list(path: Path, payload: dict[str, Any]) -> None:
    """
    JSON 리스트 파일 끝에 단일 객체를 추가 저장한다.

    Args:
        path: 대상 JSON 파일 경로
        payload: 추가할 레코드 사전
    """
    rows = read_json(path, [])
    normalized = rows if isinstance(rows, list) else []
    normalized.append(payload)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(normalized, ensure_ascii=False, indent=2), encoding="utf-8")


def promise_projects() -> list[dict[str, Any]]:
    """
    Promise 프로젝트 목록을 반환한다.

    Returns:
        프로젝트 사전 목록
    """
    payload = read_json(PROMISE_PROJECTS_PATH, [])
    return payload if isinstance(payload, list) else []


def promise_costs() -> list[dict[str, Any]]:
    """
    Promise 프로젝트 비용 요약 목록을 반환한다.

    Returns:
        비용 요약 사전 목록
    """
    payload = read_json(PROMISE_COSTS_PATH, [])
    return payload if isinstance(payload, list) else []


def meeting_rooms() -> list[dict[str, Any]]:
    """
    회의실 마스터 목록을 반환한다.

    Returns:
        회의실 사전 목록
    """
    return load_meeting_rooms(path=MEETING_ROOMS_PATH)


def finance_projects() -> list[dict[str, Any]]:
    """
    프로젝트/비용 데이터를 결합해 비용정산 조회용 목록을 만든다.

    Returns:
        비용정산 조회용 프로젝트 목록
    """
    projects = promise_projects()
    cost_by_project = {
        str(item.get("project_number", "")).strip(): item
        for item in promise_costs()
        if isinstance(item, dict)
    }

    rows: list[dict[str, Any]] = []
    for item in projects:
        if not isinstance(item, dict):
            continue
        project_number = str(item.get("project_number", "")).strip()
        if not project_number:
            continue

        cost = cost_by_project.get(project_number, {})
        expense_budget_total = int(cost.get("final_cost_total") or 0)
        used_amount = int(cost.get("execution_total") or 0)
        remaining_amount = max(expense_budget_total - used_amount, 0)

        rows.append(
            {
                "project_number": project_number,
                "project_name": str(item.get("project_name") or project_number),
                "project_type": str(item.get("project_type") or "-"),
                "status": str(item.get("status") or "-"),
                "expense_budget_total": expense_budget_total,
                "used_amount": used_amount,
                "remaining_amount": remaining_amount,
                "allowed_categories": ["교통비", "식비", "숙박비", "소모품비"],
            }
        )
    return rows


def resolve_public_base_url(request: Request) -> str:
    """
    요청 문맥에서 Add-in용 공개 베이스 URL을 계산한다.

    Args:
        request: FastAPI 요청 객체

    Returns:
        공개 베이스 URL
    """
    from_env = str(os.getenv("MOLDUBOT_PUBLIC_BASE_URL", "")).strip().rstrip("/")
    if from_env:
        return from_env
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")
