from __future__ import annotations

import asyncio
import html
import json
import time
from datetime import datetime
from pathlib import Path
from typing import Any, AsyncIterator

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse, HTMLResponse, StreamingResponse

from app.agents.report_agent import (
    compute_weekly_windows,
    generate_report_html_fast,
    generate_weekly_report_html_fast,
)
from app.api.contracts import ReportGenerateRequest, WeeklyReportGenerateRequest
from app.core.logging_config import get_logger
from app.services.mail_search_service import MailSearchService
from app.services.report_docx_service import (
    convert_html_to_docx,
    resolve_report_file_path,
    resolve_report_html_path,
)

router = APIRouter()
logger = get_logger(__name__)
ROOT_DIR = Path(__file__).resolve().parents[2]
MAIL_DB_PATH = ROOT_DIR / "data" / "sqlite" / "emails.db"
_MAIL_SEARCH_SERVICE = MailSearchService(db_path=MAIL_DB_PATH)

STEP_LABELS: dict[str, str] = {
    "1": "이메일 분석 중...",
    "2": "핵심 내용 정리 중...",
    "3": "보고서 작성 중...",
    "DONE": "DOCX 변환 중...",
}


def _encode_sse_data(payload: dict[str, Any]) -> str:
    """
    SSE data 블록 문자열을 생성한다.

    Args:
        payload: 전송할 JSON 직렬화 가능한 객체

    Returns:
        SSE 포맷 문자열
    """
    return f"event: message\ndata: {json.dumps(payload, ensure_ascii=False)}\n\n"


def _build_report_generation_input(
    email_content: str,
    email_subject: str,
    email_received_date: str,
    email_sender: str,
) -> str:
    """
    보고서 생성 모델 입력 텍스트를 구성한다.

    Args:
        email_content: 메일 본문
        email_subject: 메일 제목
        email_received_date: 기준 날짜
        email_sender: 발신자

    Returns:
        메타+본문이 포함된 단일 프롬프트 텍스트
    """
    subject = str(email_subject or "").strip() or "메일 보고서"
    received_date = str(email_received_date or "").strip() or "미상"
    sender = str(email_sender or "").strip() or "미상"
    body = str(email_content or "").strip()
    return (
        "[메일 메타]\n"
        f"- 제목: {subject}\n"
        f"- 수신일: {received_date}\n"
        f"- 발신자: {sender}\n\n"
        f"[메일 원문]\n{body}"
    )


def _build_template_report_html(subject: str, email_content: str) -> str:
    """
    모델 생성 실패 시 사용할 최소 HTML 보고서를 생성한다.

    Args:
        subject: 보고서 제목
        email_content: 메일 원문

    Returns:
        기본 HTML 문자열
    """
    raw_lines = [line.strip() for line in str(email_content or "").splitlines() if line.strip()]
    clipped = raw_lines[:10]
    items = "".join(f"<li>{html.escape(line)}</li>" for line in clipped) or "<li>원문 본문이 비어 있습니다.</li>"
    safe_subject = html.escape(str(subject or "메일 보고서"))
    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<title>보고서</title></head><body>"
        f"<h1>{safe_subject}</h1>"
        "<h2>1. 개요</h2><p>모델 출력이 비어 템플릿으로 생성했습니다.</p>"
        "<h2>2. 근거 요약</h2>"
        f"<ul>{items}</ul>"
        "<h2>3. 조치 필요 사항</h2><ul><li>담당자 검토 후 보완 필요</li></ul>"
        "</body></html>"
    )


def _build_template_weekly_report_html(
    title: str,
    actual_start: str,
    actual_end: str,
    plan_start: str,
    plan_end: str,
    report_date: str,
    author: str,
) -> str:
    """
    주간보고 모델 생성 실패 시 사용할 기본 HTML을 생성한다.

    Args:
        title: 보고서 제목
        actual_start: 실적 시작일
        actual_end: 실적 종료일
        plan_start: 계획 시작일
        plan_end: 계획 종료일
        report_date: 보고서 작성일
        author: 작성자

    Returns:
        기본 주간보고 HTML 문자열
    """
    safe_title = html.escape(title)
    safe_author = html.escape(author or "미상")
    return (
        "<!doctype html><html lang='ko'><head><meta charset='utf-8'>"
        "<title>주간보고</title>"
        "<style>"
        "body{font-family:'Malgun Gothic','맑은 고딕',sans-serif;margin:0;padding:22px;background:#fff;color:#1f1f1f;}"
        ".wrap{max-width:1360px;margin:0 auto;}"
        ".title{font-size:34px;font-weight:800;color:#1f4e79;margin:0 0 12px;}"
        ".meta{font-size:15px;line-height:1.55;margin:0 0 16px;}"
        "table{width:100%;border-collapse:collapse;table-layout:fixed;}"
        "th,td{border:1px solid #c9cfda;padding:10px 12px;vertical-align:top;font-size:14px;line-height:1.45;}"
        "th{background:#1f4e79;color:#fff;font-weight:700;}"
        "td ul{margin:0;padding-left:18px;}"
        "</style></head><body><div class='wrap'>"
        f"<h1 class='title'>{safe_title}</h1>"
        f"<p class='meta'>일시: {report_date}<br>작성자: {safe_author}</p>"
        "<table><thead><tr><th style='width:20%'>구분</th>"
        f"<th>실적 ({actual_start} ~ {actual_end})</th>"
        f"<th>계획 ({plan_start} ~ {plan_end})</th>"
        "</tr></thead><tbody>"
        "<tr><td><strong>주요 진행 상황</strong></td><td><ul><li>근거 기반 메일 요약 정리 필요<br>- 주요 요청/진행 맥락을 항목별로 재정리합니다.</li></ul></td><td><ul><li>다음 주 우선순위 상세화 필요<br>- 실행 순서와 완료 기준을 명확히 정의합니다.</li></ul></td></tr>"
        "<tr><td><strong>이슈</strong></td><td><ul><li>근거 메일 수가 적어 일부 항목은 근거 부족<br>- 추가 근거 확보 전까지 가정성 표현을 제한합니다.</li></ul></td><td><ul><li>추가 메일/회의 근거 확보 후 보강 필요<br>- 회의록/답장 메일 수집 후 내용을 보완합니다.</li></ul></td></tr>"
        "<tr><td><strong>Action Item</strong></td><td><ul><li>담당: 미상 / 기한: 미상 / 조치: 데이터 보강<br>- 담당자 확정 후 근거 데이터 누락분을 채웁니다.</li></ul></td>"
        "<td><ul><li>담당: 미상 / 기한: 미상 / 조치: 계획 확정<br>- 계획 승인 기준과 일정 리스크를 함께 점검합니다.</li></ul></td></tr>"
        "</tbody></table></div></body></html>"
    )


def _fetch_weekly_mail_items(start_date: str, end_date: str, limit: int = 30) -> list[dict[str, str]]:
    """
    주간보고 작성 대상 메일 목록을 조회한다.

    Args:
        start_date: 조회 시작일(YYYY-MM-DD)
        end_date: 조회 종료일(YYYY-MM-DD)
        limit: 최대 조회 수

    Returns:
        메일 결과 목록
    """
    payload = _MAIL_SEARCH_SERVICE.search(
        query="",
        person="",
        start_date=start_date,
        end_date=end_date,
        limit=limit,
    )
    results = payload.get("results", [])
    if not isinstance(results, list):
        return []
    typed_results: list[dict[str, str]] = []
    for item in results:
        if isinstance(item, dict):
            typed_results.append(item)
    return typed_results


@router.post("/report/generate")
async def generate_report(request: ReportGenerateRequest) -> StreamingResponse:
    """
    보고서 생성 진행 상황을 SSE로 반환한다.

    Args:
        request: 보고서 생성 요청 객체

    Returns:
        단계/완료/오류 이벤트를 포함한 SSE 응답
    """

    async def event_generator() -> AsyncIterator[str]:
        started_at = time.perf_counter()
        email_content = str(request.email_content or "").strip()
        if not email_content:
            yield _encode_sse_data({"type": "error", "message": "email_content가 비어 있습니다."})
            return

        subject = str(request.email_subject or "메일 보고서").strip() or "메일 보고서"
        report_date = datetime.now().strftime("%Y-%m-%d")
        author = str(request.email_sender or "").strip() or "미상"
        report_input = _build_report_generation_input(
            email_content=email_content,
            email_subject=subject,
            email_received_date=report_date,
            email_sender=author,
        )

        logger.info(
            "report.generate.started: subject=%s report_date=%s author=%s content_length=%s",
            subject,
            report_date,
            author,
            len(email_content),
        )

        try:
            yield _encode_sse_data({"type": "step", "step": "1", "label": STEP_LABELS["1"], "status": "running"})
            await asyncio.sleep(0)
            yield _encode_sse_data({"type": "step", "step": "1", "label": "이메일 분석 완료", "status": "done"})

            yield _encode_sse_data({"type": "step", "step": "2", "label": STEP_LABELS["2"], "status": "running"})
            await asyncio.sleep(0)
            yield _encode_sse_data({"type": "step", "step": "2", "label": "핵심 내용 정리 완료", "status": "done"})

            yield _encode_sse_data({"type": "step", "step": "3", "label": STEP_LABELS["3"], "status": "running"})
            model_started_at = time.perf_counter()
            report_html = await asyncio.to_thread(
                generate_report_html_fast,
                subject,
                report_input,
                report_date,
                author,
            )
            model_elapsed_ms = round((time.perf_counter() - model_started_at) * 1000.0, 1)
            if not report_html:
                report_html = _build_template_report_html(subject=subject, email_content=report_input)
                logger.warning("report.generate.template_fallback_used: html_length=%s", len(report_html))
            logger.info("report.generate.model_completed: elapsed_ms=%s html_length=%s", model_elapsed_ms, len(report_html))
            yield _encode_sse_data({"type": "step", "step": "3", "label": "보고서 작성 완료", "status": "done"})

            yield _encode_sse_data({"type": "step", "step": "DONE", "label": STEP_LABELS["DONE"], "status": "running"})
            docx_url = await convert_html_to_docx(html=report_html, title=subject)
            preview_url = docx_url.replace("/report/download/", "/report/preview/", 1)
            yield _encode_sse_data({"type": "step", "step": "DONE", "label": "DOCX 변환 완료", "status": "done"})

            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 1)
            logger.info(
                "report.generate.completed: elapsed_ms=%s html_length=%s docx_url=%s",
                elapsed_ms,
                len(report_html),
                docx_url,
            )
            yield _encode_sse_data({"type": "done", "docx_url": docx_url, "preview_url": preview_url})
        except Exception as exc:
            logger.exception("report.generate.failed: %s", exc)
            yield _encode_sse_data({"type": "error", "message": f"보고서 생성 중 오류: {exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.post("/report/weekly/generate")
async def generate_weekly_report(request: WeeklyReportGenerateRequest) -> StreamingResponse:
    """
    주간보고 생성 진행 상황을 SSE로 반환한다.

    Args:
        request: 주간보고 생성 요청

    Returns:
        단계/완료/오류 이벤트를 포함한 SSE 응답
    """

    async def event_generator() -> AsyncIterator[str]:
        started_at = time.perf_counter()
        try:
            week_offset = max(1, min(8, int(request.week_offset)))
        except (TypeError, ValueError):
            week_offset = 1
        author = str(request.report_author or "").strip() or "미상"
        window = compute_weekly_windows(week_offset=week_offset, reference_date="")
        title = str(window.get("title") or "주간보고")
        logger.info(
            "weekly_report.generate.started: week_offset=%s actual=%s~%s plan=%s~%s",
            week_offset,
            window["actual_start"],
            window["actual_end"],
            window["plan_start"],
            window["plan_end"],
        )
        try:
            yield _encode_sse_data({"type": "step", "step": "1", "label": "주간 메일 조회 중...", "status": "running"})
            mail_items = await asyncio.to_thread(
                _fetch_weekly_mail_items,
                window["actual_start"],
                window["actual_end"],
                30,
            )
            yield _encode_sse_data({"type": "step", "step": "1", "label": "주간 메일 조회 완료", "status": "done"})
            yield _encode_sse_data({"type": "step", "step": "2", "label": "주요 내용 정리 중...", "status": "running"})
            await asyncio.sleep(0)
            yield _encode_sse_data({"type": "step", "step": "2", "label": "주요 내용 정리 완료", "status": "done"})

            yield _encode_sse_data({"type": "step", "step": "3", "label": "주간보고 작성 중...", "status": "running"})
            report_html = await asyncio.to_thread(
                generate_weekly_report_html_fast,
                mail_items,
                week_offset,
                author,
                "",
            )
            if not report_html:
                report_html = _build_template_weekly_report_html(
                    title=title,
                    actual_start=window["actual_start"],
                    actual_end=window["actual_end"],
                    plan_start=window["plan_start"],
                    plan_end=window["plan_end"],
                    report_date=window["report_date"],
                    author=author,
                )
                logger.warning("weekly_report.generate.template_fallback_used: html_length=%s", len(report_html))
            yield _encode_sse_data({"type": "step", "step": "3", "label": "주간보고 작성 완료", "status": "done"})

            yield _encode_sse_data({"type": "step", "step": "DONE", "label": "DOCX 변환 중...", "status": "running"})
            docx_url = await convert_html_to_docx(html=report_html, title=title, layout="landscape_wide")
            preview_url = docx_url.replace("/report/download/", "/report/preview/", 1)
            yield _encode_sse_data({"type": "step", "step": "DONE", "label": "DOCX 변환 완료", "status": "done"})
            elapsed_ms = round((time.perf_counter() - started_at) * 1000.0, 1)
            logger.info(
                "weekly_report.generate.completed: elapsed_ms=%s items=%s html_length=%s docx_url=%s",
                elapsed_ms,
                len(mail_items),
                len(report_html),
                docx_url,
            )
            yield _encode_sse_data(
                {
                    "type": "done",
                    "docx_url": docx_url,
                    "preview_url": preview_url,
                    "report_title": title,
                }
            )
        except Exception as exc:
            logger.exception("weekly_report.generate.failed: %s", exc)
            yield _encode_sse_data({"type": "error", "message": f"주간보고 생성 중 오류: {exc}"})

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={"Cache-Control": "no-cache", "X-Accel-Buffering": "no"},
    )


@router.get("/report/download/{filename}")
async def download_report(filename: str) -> FileResponse:
    """
    생성된 DOCX 보고서를 다운로드한다.

    Args:
        filename: DOCX 파일명

    Returns:
        DOCX 파일 응답
    """
    path = resolve_report_file_path(filename=filename)
    if not path.exists():
        raise HTTPException(status_code=404, detail="보고서 파일을 찾을 수 없습니다.")
    return FileResponse(
        str(path),
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=path.name,
    )


@router.get("/report/preview/{filename}")
async def preview_report(filename: str, request: Request) -> HTMLResponse:
    """
    HTML 보고서 미리보기 페이지를 반환한다.

    Args:
        filename: DOCX 파일명
        request: FastAPI request

    Returns:
        iframe(srcdoc) 기반 미리보기 HTML
    """
    docx_path = resolve_report_file_path(filename=filename)
    if not docx_path.exists():
        raise HTTPException(status_code=404, detail="보고서 파일을 찾을 수 없습니다.")

    html_path = resolve_report_html_path(filename=filename)
    rendered_html = html_path.read_text(encoding="utf-8") if html_path.exists() else "<p>미리보기 HTML이 없습니다.</p>"
    escaped_srcdoc = html.escape(rendered_html, quote=True)
    download_url = str(request.url_for("download_report", filename=docx_path.name))

    page_html = f"""<!doctype html>
<html lang=\"ko\">
<head>
  <meta charset=\"utf-8\">
  <meta name=\"viewport\" content=\"width=device-width, initial-scale=1\">
  <title>보고서 미리보기</title>
  <style>
    :root {{
      --bg: #f7f5f2;
      --panel: #ffffff;
      --line: #d9d3ca;
      --text: #22201c;
      --muted: #6d665d;
      --primary: #a86f46;
      --primary-hover: #935f3e;
    }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; background: var(--bg); color: var(--text); font-family: "Pretendard", "SUIT", "Apple SD Gothic Neo", "Malgun Gothic", sans-serif; }}
    .wrap {{ max-width: 1120px; margin: 0 auto; padding: 14px; }}
    .topbar {{ display:flex; justify-content:space-between; align-items:center; gap:8px; border:1px solid var(--line); border-radius:12px; background:var(--panel); padding:10px 12px; margin-bottom:10px; }}
    .title {{ font-size:14px; font-weight:700; }}
    .btn {{ text-decoration:none; border-radius:10px; border:0; background:var(--primary); color:#fff; font-size:12px; font-weight:700; padding:8px 14px; }}
    .btn:hover {{ background: var(--primary-hover); }}
    .panel {{ border:1px solid var(--line); border-radius:14px; background:var(--panel); min-height:calc(100vh - 120px); overflow:hidden; }}
    iframe {{ width:100%; height:calc(100vh - 120px); border:0; background:#fff; }}
  </style>
</head>
<body>
  <div class=\"wrap\">
    <div class=\"topbar\">
      <div class=\"title\">보고서 미리보기</div>
      <a class=\"btn\" href=\"{download_url}\">다운로드</a>
    </div>
    <div class=\"panel\">
      <iframe title=\"보고서\" srcdoc=\"{escaped_srcdoc}\"></iframe>
    </div>
  </div>
</body>
</html>"""
    return HTMLResponse(content=page_html)
