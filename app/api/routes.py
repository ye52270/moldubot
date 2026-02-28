from __future__ import annotations

import json
import mimetypes
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import Response, StreamingResponse
from openai import OpenAIError
from pydantic import BaseModel, Field

from app.agents.deep_chat_agent import get_deep_chat_agent, is_openai_key_configured
from app.core.logging_config import get_logger

ROOT_DIR = Path(__file__).resolve().parents[2]
PROMISE_PROJECTS_PATH = ROOT_DIR / "clients" / "portals" / "myPromise" / "projects.json"
PROMISE_COSTS_PATH = ROOT_DIR / "clients" / "portals" / "myPromise" / "project_costs.json"
MEETING_ROOMS_PATH = ROOT_DIR / "data" / "mock" / "meeting_rooms.json"
CLIENT_LOG_PATH = ROOT_DIR / "data" / "mock" / "client_logs.ndjson"
ADDIN_MANIFEST_PATH = ROOT_DIR / "clients" / "outlook-addin" / "manifest.xml"

router = APIRouter()
logger = get_logger(__name__)


class ChatRequest(BaseModel):
    message: str = ""
    thread_id: str | None = None
    mode: str | None = None
    email_id: str | None = None
    intent_name: str | None = None
    runtime_options: dict[str, Any] | None = None


class IntentResolveRequest(BaseModel):
    message: str = ""
    context: dict[str, Any] | None = None


class SearchByIdRequest(BaseModel):
    id: str = Field(default="")


class ConfirmRequest(BaseModel):
    thread_id: str = Field(default="")
    approved: bool = False
    confirm_token: str | None = None


class RoomBookingRequest(BaseModel):
    building: str
    floor: int
    room_name: str
    subject: str
    date: str
    start_time: str
    end_time: str
    body: str | None = ""


class WeeklyReportExportRequest(BaseModel):
    format: str = "docx"
    markdown: str = ""
    file_name: str = "weekly-report"


def _read_json(path: Path, default: Any) -> Any:
    if not path.exists():
        return default
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return default


def _write_ndjson(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as fp:
        fp.write(json.dumps(payload, ensure_ascii=False) + "\n")


def _promise_projects() -> list[dict[str, Any]]:
    payload = _read_json(PROMISE_PROJECTS_PATH, [])
    return payload if isinstance(payload, list) else []


def _promise_costs() -> list[dict[str, Any]]:
    payload = _read_json(PROMISE_COSTS_PATH, [])
    return payload if isinstance(payload, list) else []


def _meeting_rooms() -> list[dict[str, Any]]:
    payload = _read_json(MEETING_ROOMS_PATH, [])
    return payload if isinstance(payload, list) else []


def _finance_projects() -> list[dict[str, Any]]:
    projects = _promise_projects()
    cost_by_project = {
        str(item.get("project_number", "")).strip(): item
        for item in _promise_costs()
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


def _resolve_public_base_url(request: Request) -> str:
    from_env = str(os.getenv("MOLDUBOT_PUBLIC_BASE_URL", "")).strip().rstrip("/")
    if from_env:
        return from_env
    proto = request.headers.get("x-forwarded-proto") or request.url.scheme or "https"
    host = request.headers.get("x-forwarded-host") or request.headers.get("host") or request.url.netloc
    return f"{proto}://{host}".rstrip("/")


@router.get("/healthz")
def healthz() -> dict[str, str]:
    return {"status": "ok"}


@router.get("/addin/manifest.xml", include_in_schema=False)
def addin_manifest(request: Request) -> Response:
    xml = ADDIN_MANIFEST_PATH.read_text(encoding="utf-8")
    base_url = _resolve_public_base_url(request)
    # Existing manifest uses a fixed ngrok URL. Replace it on-the-fly for current host.
    xml = xml.replace("https://brendon-unboding-maliciously.ngrok-free.dev", base_url)
    return Response(content=xml, media_type="application/xml")


@router.get("/search/chat/runtime-config")
def search_chat_runtime_config() -> dict[str, int]:
    return {
        "sticky_current_mail_ttl_ms": 10 * 60 * 1000,
        "sticky_current_mail_max_turns": 4,
        "followup_state_ttl_sec": 600,
    }


@router.post("/search/chat")
def search_chat(payload: ChatRequest) -> dict[str, Any]:
    """
    채팅 요청을 처리하고 deep agent 응답을 반환한다.

    Args:
        payload: 채팅 요청 본문

    Returns:
        상태/스레드/응답/메타데이터를 포함한 표준 응답 객체
    """
    text = str(payload.message or "").strip()
    preview = (text[:80] + "...") if len(text) > 80 else text
    logger.info("search_chat 요청 수신: length=%s preview=%s", len(text), preview)

    if not text:
        answer = "요청 내용을 입력해 주세요."
        source = "validation"
        logger.info("search_chat 검증 실패: 빈 입력")
    elif not is_openai_key_configured():
        answer = "서버에 OPENAI_API_KEY가 설정되지 않아 답변을 생성할 수 없습니다."
        source = "missing-openai-key"
        logger.warning("search_chat 환경 누락: OPENAI_API_KEY 미설정")
    else:
        try:
            answer = get_deep_chat_agent().respond(text)
            source = "deep-agent"
            logger.info("search_chat 처리 완료: source=%s answer_length=%s", source, len(answer))
        except OpenAIError as exc:
            logger.error("OpenAI 호출 실패: %s", exc)
            answer = "OpenAI 호출에 실패했습니다. 잠시 후 다시 시도해 주세요."
            source = "openai-error"

    return {
        "status": "completed",
        "thread_id": payload.thread_id or f"outlook_{int(datetime.now(tz=timezone.utc).timestamp())}",
        "answer": answer,
        "metadata": {"source": source},
    }


@router.post("/search/chat/confirm")
def search_chat_confirm(payload: ConfirmRequest) -> dict[str, Any]:
    if payload.approved:
        return {
            "status": "completed",
            "thread_id": payload.thread_id,
            "answer": "승인 처리되었습니다. (개발 서버 기본 동작)",
            "metadata": {"confirm": {"approved": True}},
        }
    return {
        "status": "completed",
        "thread_id": payload.thread_id,
        "answer": "요청을 취소했습니다.",
        "metadata": {"confirm": {"approved": False}},
    }


@router.post("/intents/resolve")
def intents_resolve(payload: IntentResolveRequest) -> dict[str, Any]:
    text = str(payload.message or "").lower()
    if "회의실" in text or "회의" in text:
        intent = "room_booking"
    elif "근태" in text:
        intent = "hr_apply"
    elif "비용" in text or "정산" in text:
        intent = "finance"
    elif "실행예산" in text or "promise" in text:
        intent = "promise"
    else:
        intent = "chat"
    return {
        "intent": intent,
        "primary_intent": intent,
        "confidence": 0.7,
        "router_version": "bootstrap-v1",
    }


@router.post("/search/id")
def search_by_id(payload: SearchByIdRequest) -> dict[str, Any]:
    raw = str(payload.id or "").strip()
    return {
        "found": bool(raw),
        "message_id": raw,
        "open_message_id": raw,
        "resolved_by": "passthrough",
    }


@router.get("/api/meeting-rooms")
def meeting_rooms(building: str | None = None, floor: int | None = None) -> dict[str, Any]:
    rooms = _meeting_rooms()

    if not building:
        buildings = sorted({str(item.get("building", "")).strip() for item in rooms if item.get("building")})
        return {
            "items": [{"building": name} for name in buildings],
            "count": len(buildings),
        }

    if building and floor is None:
        floors = sorted(
            {
                int(item.get("floor"))
                for item in rooms
                if str(item.get("building", "")).strip() == building and item.get("floor") is not None
            }
        )
        return {
            "items": [{"building": building, "floor": value} for value in floors],
            "count": len(floors),
        }

    filtered = [
        item
        for item in rooms
        if str(item.get("building", "")).strip() == building and int(item.get("floor", -1)) == int(floor)
    ]
    return {"items": filtered, "count": len(filtered)}


@router.post("/api/meeting-rooms/book")
def meeting_room_book(payload: RoomBookingRequest) -> dict[str, Any]:
    answer = (
        f"{payload.date} {payload.start_time}-{payload.end_time} "
        f"{payload.building} {payload.floor}층 {payload.room_name} 예약 요청을 접수했습니다."
    )
    return {
        "status": "completed",
        "answer": answer,
        "booking": payload.model_dump(),
    }


@router.get("/api/promise/projects")
def promise_projects() -> dict[str, Any]:
    projects = _promise_projects()
    return {"projects": projects, "count": len(projects)}


@router.get("/api/promise/projects/{project_number}/summary")
def promise_project_summary(project_number: str) -> dict[str, Any]:
    target = str(project_number or "").strip()
    for item in _promise_costs():
        if str(item.get("project_number", "")).strip() == target:
            return item
    raise HTTPException(status_code=404, detail="프로젝트 요약을 찾지 못했습니다.")


@router.get("/api/finance/projects")
def finance_projects() -> dict[str, Any]:
    projects = _finance_projects()
    return {"projects": projects, "count": len(projects)}


@router.get("/api/finance/projects/{project_number}/budget")
def finance_project_budget(project_number: str) -> dict[str, Any]:
    target = str(project_number or "").strip()
    for item in _finance_projects():
        if str(item.get("project_number", "")).strip() == target:
            return item
    raise HTTPException(status_code=404, detail="비용정산 예산 정보를 찾지 못했습니다.")


@router.post("/addin/client-logs", status_code=204)
async def addin_client_logs(request: Request) -> Response:
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        raw = await request.body()
        payload = {"raw": raw.decode("utf-8", errors="replace")}

    _write_ndjson(
        CLIENT_LOG_PATH,
        {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "payload": payload,
        },
    )
    return Response(status_code=204)


@router.post("/addin/export/weekly-report")
def addin_export_weekly_report(payload: WeeklyReportExportRequest) -> StreamingResponse:
    file_name = str(payload.file_name or "weekly-report").strip() or "weekly-report"
    markdown = str(payload.markdown or "")

    # Minimal bootstrap output: plain-text payload with DOCX mime so the UI download flow works.
    text = (
        "MolduBot Weekly Report (Bootstrap Server)\n"
        "======================================\n\n"
        f"Generated at: {datetime.now(tz=timezone.utc).isoformat()}\n\n"
        f"{markdown}\n"
    )
    content = text.encode("utf-8")
    media_type = (
        "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )
    ext = mimetypes.guess_extension(media_type) or ".docx"
    safe_name = "".join(ch for ch in file_name if ch.isalnum() or ch in ("-", "_")) or "weekly-report"

    return StreamingResponse(
        BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}{ext}"'},
    )
