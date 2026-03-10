from __future__ import annotations

import json
import mimetypes
import os
from datetime import datetime, timezone
from io import BytesIO
from pathlib import Path
from typing import Any

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import Response, StreamingResponse

from app.api.contracts import ChatEvalPipelineRunRequest, ChatEvalRunRequest, WeeklyReportExportRequest
from app.api.data_access import CLIENT_LOG_PATH, write_ndjson
from app.core.logging_config import get_logger
from app.services.chat_eval_service import (
    DEFAULT_JUDGE_MODEL,
    list_chat_eval_cases,
    load_latest_chat_eval_report,
    run_chat_eval_session,
)
from app.services.chat_eval_history_store import get_chat_eval_run, list_chat_eval_runs
from app.services.chat_eval_pipeline_service import (
    load_latest_chat_eval_pipeline_report,
    render_pipeline_report_markdown,
    run_chat_eval_pipeline,
)

router = APIRouter()
logger = get_logger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[2]
NOISY_CLIENT_EVENTS = {
    "selection_context_polled_snapshot",
    "selection_context_effective_send",
}


@router.post("/addin/client-logs", status_code=204)
async def addin_client_logs(request: Request) -> Response:
    """
    Add-in 클라이언트 로그를 NDJSON으로 저장한다.

    Args:
        request: FastAPI 요청 객체

    Returns:
        204 No Content
    """
    content_type = request.headers.get("content-type", "")
    if "application/json" in content_type:
        payload = await request.json()
    else:
        raw = await request.body()
        payload = {"raw": raw.decode("utf-8", errors="replace")}

    write_ndjson(
        CLIENT_LOG_PATH,
        {
            "ts": datetime.now(tz=timezone.utc).isoformat(),
            "payload": payload,
        },
    )
    payload_dict = payload if isinstance(payload, dict) else {"raw": str(payload)}
    event_name = str(payload_dict.get("event") or payload_dict.get("message") or "unknown")
    level = str(payload_dict.get("level") or "info")
    if event_name in NOISY_CLIENT_EVENTS and level.lower() == "info":
        return Response(status_code=204)
    logger.info(
        "addin_client_logs 수신: level=%s event=%s payload=%s",
        level,
        event_name,
        str(payload_dict.get("payload") or payload_dict.get("raw") or "")[:280],
    )
    return Response(status_code=204)


@router.post("/addin/export/weekly-report")
def addin_export_weekly_report(payload: WeeklyReportExportRequest) -> StreamingResponse:
    """
    주간보고서 Markdown을 DOCX mime 타입 바이너리로 다운로드 제공한다.

    Args:
        payload: 보고서 내보내기 요청

    Returns:
        DOCX 다운로드 스트림
    """
    file_name = str(payload.file_name or "weekly-report").strip() or "weekly-report"
    markdown = str(payload.markdown or "")
    text = (
        "MolduBot Weekly Report (Bootstrap Server)\n"
        "======================================\n\n"
        f"Generated at: {datetime.now(tz=timezone.utc).isoformat()}\n\n"
        f"{markdown}\n"
    )
    content = text.encode("utf-8")
    media_type = "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    ext = mimetypes.guess_extension(media_type) or ".docx"
    safe_name = "".join(ch for ch in file_name if ch.isalnum() or ch in ("-", "_")) or "weekly-report"
    return StreamingResponse(
        BytesIO(content),
        media_type=media_type,
        headers={"Content-Disposition": f'attachment; filename="{safe_name}{ext}"'},
    )


@router.post("/qa/chat-eval/run")
def run_chat_eval(payload: ChatEvalRunRequest, request: Request) -> dict[str, Any]:
    """
    E2E 채팅 평가를 실행하고 LLM-as-Judge 리포트를 반환한다.

    Args:
        payload: 평가 실행 옵션
        request: FastAPI 요청 객체

    Returns:
        실행 완료 리포트 JSON
    """
    chat_url = str(payload.chat_url or "").strip()
    if not chat_url:
        chat_url = str(request.base_url).rstrip("/") + "/search/chat"
    judge_model = str(payload.judge_model or "").strip() or DEFAULT_JUDGE_MODEL
    selected_email_id = str(payload.selected_email_id or "").strip()
    mailbox_user = str(payload.mailbox_user or "").strip()
    if selected_email_id and not mailbox_user:
        raise HTTPException(
            status_code=400,
            detail="selected_email_id를 지정한 경우 mailbox_user도 함께 제공해야 합니다.",
        )
    try:
        report = run_chat_eval_session(
            chat_url=chat_url,
            judge_model=judge_model,
            case_ids=payload.case_ids,
            cases_file=str(payload.cases_file or "").strip() or None,
            selected_email_id=selected_email_id,
            mailbox_user=mailbox_user,
            request_timeout_sec=max(10, int(payload.request_timeout_sec or 90)),
            max_cases=payload.max_cases,
        )
    except Exception as exc:
        logger.exception("chat_eval.run.failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"chat_eval_run_failed: {type(exc).__name__}: {exc}",
        ) from exc
    return {"status": "completed", "report": report}


@router.get("/qa/chat-eval/latest")
def chat_eval_latest() -> dict[str, Any]:
    """
    최근 저장된 E2E 채팅 평가 리포트를 조회한다.

    Returns:
        저장된 리포트 또는 not-found 상태
    """
    latest = load_latest_chat_eval_report()
    if latest is None:
        return {"status": "not-found"}
    return {"status": "completed", "report": latest}


@router.get("/qa/chat-eval/cases")
def chat_eval_cases(cases_file: str = Query(default="")) -> dict[str, Any]:
    """
    채팅 평가 케이스 목록을 반환한다.

    Returns:
        평가 케이스 배열
    """
    normalized_cases_file = str(cases_file or "").strip() or None
    cases = list_chat_eval_cases(cases_file=normalized_cases_file)
    return {"status": "completed", "count": len(cases), "cases": cases}


@router.get("/qa/chat-eval/defaults")
def chat_eval_defaults() -> dict[str, Any]:
    """
    Chat Eval UI 기본값을 반환한다.

    Returns:
        judge/mailbox 기본값 사전
    """
    judge_model = str(os.getenv("MOLDUBOT_JUDGE_MODEL", "")).strip() or DEFAULT_JUDGE_MODEL
    return {
        "status": "completed",
        "defaults": {
            "judge_model": judge_model,
            "mailbox_user": "jaeyoung_dev@outlook.com",
        },
    }


@router.get("/qa/chat-eval/history")
def chat_eval_history(limit: int = Query(default=20, ge=1, le=200)) -> dict[str, Any]:
    """
    Chat Eval 실행 이력 요약 목록을 반환한다.

    Args:
        limit: 최대 조회 건수

    Returns:
        이력 목록 JSON
    """
    runs = list_chat_eval_runs(limit=limit)
    return {"status": "completed", "count": len(runs), "runs": runs}


@router.get("/qa/chat-eval/history/{run_no}")
def chat_eval_history_detail(run_no: int) -> dict[str, Any]:
    """
    Chat Eval 실행 차수 상세 리포트를 반환한다.

    Args:
        run_no: 실행 차수

    Returns:
        실행 리포트 JSON
    """
    report = get_chat_eval_run(run_no=run_no)
    if report is None:
        raise HTTPException(status_code=404, detail="chat_eval_history_not_found")
    return {"status": "completed", "report": report}


@router.post("/qa/chat-eval/pipeline/run")
def run_chat_eval_pipeline_route(payload: ChatEvalPipelineRunRequest, request: Request) -> dict[str, Any]:
    """
    Chat E2E 평가 파이프라인을 실행한다(실행 + baseline 비교 + 품질게이트).

    Args:
        payload: 파이프라인 실행 옵션
        request: FastAPI 요청 객체

    Returns:
        파이프라인 실행 리포트 JSON
    """
    chat_url = str(payload.chat_url or "").strip()
    if not chat_url:
        chat_url = str(request.base_url).rstrip("/") + "/search/chat"
    selected_email_id = str(payload.selected_email_id or "").strip()
    mailbox_user = str(payload.mailbox_user or "").strip()
    if selected_email_id and not mailbox_user:
        raise HTTPException(
            status_code=400,
            detail="selected_email_id를 지정한 경우 mailbox_user도 함께 제공해야 합니다.",
        )
    try:
        pipeline_report = run_chat_eval_pipeline(
            chat_url=chat_url,
            judge_model=str(payload.judge_model or "").strip() or DEFAULT_JUDGE_MODEL,
            selected_email_id=selected_email_id,
            mailbox_user=mailbox_user,
            request_timeout_sec=max(10, int(payload.request_timeout_sec or 90)),
            max_cases=payload.max_cases,
            case_ids=payload.case_ids,
            cases_file=str(payload.cases_file or "").strip() or None,
            min_pass_rate=float(payload.min_pass_rate),
            min_avg_score=float(payload.min_avg_score),
            allow_regression_cases=max(0, int(payload.allow_regression_cases)),
        )
    except Exception as exc:
        logger.exception("chat_eval.pipeline.failed: %s", exc)
        raise HTTPException(
            status_code=502,
            detail=f"chat_eval_pipeline_failed: {type(exc).__name__}: {exc}",
        ) from exc
    return {"status": "completed", "pipeline_report": pipeline_report}


@router.get("/qa/chat-eval/pipeline/latest")
def chat_eval_pipeline_latest() -> dict[str, Any]:
    """
    최근 저장된 chat-eval 파이프라인 리포트를 조회한다.

    Returns:
        파이프라인 리포트 또는 not-found
    """
    latest = load_latest_chat_eval_pipeline_report()
    if latest is None:
        return {"status": "not-found"}
    return {"status": "completed", "pipeline_report": latest}


@router.get("/qa/chat-eval/pipeline/download")
def chat_eval_pipeline_download(format: str = Query(default="json")) -> Response:
    """
    최근 파이프라인 리포트를 파일 다운로드 형태로 반환한다.

    Args:
        format: `json` 또는 `md`

    Returns:
        다운로드 응답
    """
    latest = load_latest_chat_eval_pipeline_report()
    if latest is None:
        raise HTTPException(status_code=404, detail="chat_eval_pipeline_report_not_found")
    normalized_format = str(format or "json").strip().lower()
    if normalized_format == "md":
        body = render_pipeline_report_markdown(report=latest)
        return Response(
            content=body,
            media_type="text/markdown; charset=utf-8",
            headers={"Content-Disposition": 'attachment; filename="chat_eval_pipeline_latest.md"'},
        )
    body = json.dumps(latest, ensure_ascii=False, indent=2)
    return Response(
        content=body,
        media_type="application/json; charset=utf-8",
        headers={"Content-Disposition": 'attachment; filename="chat_eval_pipeline_latest.json"'},
    )
