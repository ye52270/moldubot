from __future__ import annotations

import os
import re
import html
from datetime import date, datetime, timedelta
from functools import lru_cache
from zoneinfo import ZoneInfo

from openai import AzureOpenAI, OpenAIError

from app.core.azure_openai_client import get_azure_openai_client, normalize_azure_deployment_name
from app.core.logging_config import get_logger

DEFAULT_REPORT_MODEL = "gpt-4o-mini"
DEFAULT_REPORT_TIMEOUT_SEC = 90
logger = get_logger(__name__)
SEOUL_TZ = ZoneInfo("Asia/Seoul")


def _resolve_report_timeout_sec() -> int:
    """
    보고서 단일 호출 타임아웃(초)을 환경변수에서 읽어 정규화한다.

    Returns:
        10~300 범위의 정수 타임아웃 초
    """
    raw = str(os.getenv("REPORT_MODEL_TIMEOUT_SEC", str(DEFAULT_REPORT_TIMEOUT_SEC))).strip()
    try:
        timeout_sec = int(raw)
    except ValueError:
        timeout_sec = DEFAULT_REPORT_TIMEOUT_SEC
    return max(10, min(300, timeout_sec))


@lru_cache(maxsize=1)
def _get_azure_openai_client() -> AzureOpenAI:
    """
    보고서 생성에 재사용할 Azure OpenAI 클라이언트를 반환한다.

    Returns:
        Azure OpenAI SDK 클라이언트 인스턴스
    """
    return get_azure_openai_client(timeout_sec=_resolve_report_timeout_sec())


def _strip_code_fence(text: str) -> str:
    """
    모델 출력의 코드펜스를 제거한다.

    Args:
        text: 원본 출력 텍스트

    Returns:
        코드펜스 제거 문자열
    """
    value = str(text or "").strip()
    value = value.removeprefix("```html").strip()
    value = value.removeprefix("```").strip()
    if value.endswith("```"):
        value = value[:-3].strip()
    return value


def _normalize_report_date_text(report_date: str) -> str:
    """
    보고서 표지용 날짜 문자열을 정규화한다.

    Args:
        report_date: 원본 날짜 문자열

    Returns:
        YYYY-MM-DD 형식 문자열
    """
    raw = str(report_date or "").strip()
    candidate = raw[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        return candidate
    return datetime.now().strftime("%Y-%m-%d")


def _seoul_today() -> date:
    """
    서울 타임존 기준 오늘 날짜를 반환한다.

    Returns:
        서울 기준 날짜
    """
    return datetime.now(tz=SEOUL_TZ).date()


def _parse_iso_date_or_today(value: str) -> date:
    """
    ISO 날짜 문자열을 date로 변환하고 실패 시 오늘을 반환한다.

    Args:
        value: YYYY-MM-DD 또는 ISO datetime 문자열

    Returns:
        변환된 날짜
    """
    raw = str(value or "").strip()
    candidate = raw[:10]
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", candidate):
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").date()
        except ValueError:
            return _seoul_today()
    return _seoul_today()


def compute_weekly_windows(week_offset: int, reference_date: str = "") -> dict[str, str]:
    """
    주간보고용 실적/계획 주간 범위를 계산한다.

    Args:
        week_offset: 현재 주 기준 몇 주 전(1=지난주)
        reference_date: 기준일(미입력 시 서울 기준 오늘)

    Returns:
        주간 범위/라벨 정보를 담은 사전
    """
    safe_offset = max(1, min(8, int(week_offset)))
    base_date = _parse_iso_date_or_today(reference_date)
    current_monday = base_date - timedelta(days=base_date.weekday())
    actual_monday = current_monday - timedelta(days=7 * safe_offset)
    actual_friday = actual_monday + timedelta(days=4)
    plan_monday = actual_monday + timedelta(days=7)
    plan_friday = plan_monday + timedelta(days=4)
    month_week = ((actual_monday.day - 1) // 7) + 1
    title = f"주간보고 - {actual_monday.month}월 {month_week}주차"
    return {
        "title": title,
        "actual_start": actual_monday.isoformat(),
        "actual_end": actual_friday.isoformat(),
        "plan_start": plan_monday.isoformat(),
        "plan_end": plan_friday.isoformat(),
        "report_date": _seoul_today().isoformat(),
    }


def _extract_evidence_lines(email_content: str, limit: int = 14) -> list[str]:
    """
    메일 원문에서 보고서 근거 라인을 추출한다.

    Args:
        email_content: 메일 본문
        limit: 최대 라인 수

    Returns:
        근거 라인 목록
    """
    lines = [line.strip() for line in str(email_content or "").splitlines() if line.strip()]
    cleaned: list[str] = []
    for line in lines:
        compact = re.sub(r"\s+", " ", line)
        if len(compact) < 4:
            continue
        if compact in cleaned:
            continue
        cleaned.append(compact)
        if len(cleaned) >= max(4, limit):
            break
    return cleaned


def _build_fast_report_messages(
    email_subject: str,
    email_content: str,
    report_date: str,
    report_author: str,
) -> list[dict[str, str]]:
    """
    단일 모델 호출용 보고서 프롬프트 메시지를 생성한다.

    Args:
        email_subject: 메일 제목
        email_content: 메일 본문/스레드 원문
        report_date: 보고서 표지 날짜
        report_author: 보고서 작성자 표기

    Returns:
        Azure OpenAI chat.completions 메시지 배열
    """
    subject = str(email_subject or "").strip() or "메일 보고서"
    author = str(report_author or "").strip() or "미상"
    date_text = _normalize_report_date_text(report_date=report_date)
    evidence_lines = _extract_evidence_lines(email_content=email_content)
    evidence_block = "\n".join(f"- {line}" for line in evidence_lines) or "- 근거 원문 없음"
    system_prompt = (
        "당신은 IT 운영 보고서 작성 전문가다. "
        "반드시 HTML 문서만 반환하고, 코드펜스/JSON/설명 문장을 금지한다. "
        "입력 원문에 없는 사실/고유명사/날짜/조직명을 절대 생성하지 말라."
    )
    user_prompt = (
        "[고정 메타데이터]\n"
        f"- 제목: {subject}\n"
        f"- 날짜: {date_text}\n"
        f"- 작성: {author}\n\n"
        "[근거 원문]\n"
        f"{evidence_block}\n\n"
        "출력 규칙:\n"
        "1) 제목은 반드시 메일 제목과 동일하게 사용한다.\n"
        "2) 표지 메타는 날짜/작성만 넣고 수신/참조는 넣지 않는다.\n"
        "3) 원문 근거가 없는 내용은 '근거 부족'으로 명시한다.\n"
        "4) 특정 솔루션/조직/메신저(예: B톡)는 원문에 있을 때만 기술한다.\n"
        "5) 각 섹션은 2~4문장으로 구체 작성하되 과장 금지.\n"
        "6) 타임라인 표는 근거 라인에서 확인 가능한 항목만 작성한다.\n"
        "7) Action Items는 근거 기반으로만 작성하고 없으면 '추가 확인 필요' 1개를 넣는다.\n\n"
        "HTML 섹션 순서:\n"
        "1. 개요(Executive Summary)\n"
        "2. 배경 및 현황\n"
        "3. 논의 내용 타임라인(표: 날짜|주체|핵심 내용)\n"
        "4. 기술 검토 내용(4.1/4.2/4.3)\n"
        "5. 이슈 및 리스크\n"
        "6. 조치 필요 사항(Action Items 표)\n"
        "7. 참고 자료(메일 원문 기준)\n"
        "스타일: A4 max-width 210mm, Malgun Gothic, th 배경 #1f4e79/글자 #ffffff"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _build_weekly_evidence_lines(mail_items: list[dict[str, str]], limit: int = 30) -> list[str]:
    """
    주간보고 입력용 메일 근거 라인을 생성한다.

    Args:
        mail_items: 메일 검색 결과 목록
        limit: 최대 라인 수

    Returns:
        근거 라인 목록
    """
    lines: list[str] = []
    for item in mail_items:
        subject = str(item.get("subject", "")).strip() or "제목 없음"
        received = str(item.get("received_date", "")).strip()[:10] or "미상"
        sender = str(item.get("sender_names", "")).strip() or str(item.get("from_address", "")).strip() or "미상"
        summary = str(item.get("summary_text", "")).strip() or str(item.get("snippet", "")).strip()
        if not summary:
            summary = "요약 없음"
        summary = re.sub(r"\s+", " ", summary)
        lines.append(f"[{received}] {subject} | 발신자: {sender} | 요약: {summary}")
        if len(lines) >= max(10, limit):
            break
    if not lines:
        lines.append("[근거 없음] 조회된 메일이 없습니다.")
    return lines


def _build_weekly_report_messages(
    mail_items: list[dict[str, str]],
    week_offset: int,
    report_author: str,
    reference_date: str = "",
) -> list[dict[str, str]]:
    """
    주간보고 생성용 단일 호출 메시지를 생성한다.

    Args:
        mail_items: 주간 메일 검색 결과 목록
        week_offset: 몇 주 전 주간인지 나타내는 오프셋
        report_author: 작성자
        reference_date: 기준 날짜

    Returns:
        chat.completions 메시지 목록
    """
    windows = compute_weekly_windows(week_offset=week_offset, reference_date=reference_date)
    author = str(report_author or "").strip() or "미상"
    evidence_lines = _build_weekly_evidence_lines(mail_items=mail_items)
    evidence_block = "\n".join(f"- {line}" for line in evidence_lines)
    system_prompt = (
        "당신은 IT 업무 주간보고 작성 전문가다. "
        "반드시 HTML 문서만 반환하고, 코드펜스/JSON/설명 텍스트를 금지한다. "
        "근거 메일에 없는 사실은 생성하지 말고, 부족한 정보는 '근거 부족'으로 명시한다."
    )
    user_prompt = (
        "[보고서 메타]\n"
        f"- 제목: {windows['title']}\n"
        f"- 일시: {windows['report_date']}\n"
        f"- 작성자: {author}\n"
        f"- 실적 기간: {windows['actual_start']} ~ {windows['actual_end']}\n"
        f"- 계획 기간: {windows['plan_start']} ~ {windows['plan_end']}\n\n"
        "[근거 메일]\n"
        f"{evidence_block}\n\n"
        "반드시 아래 형식의 HTML로 작성:\n"
        "1) 화면 비율은 가로형(16:9) 문서 느낌, 폭이 넓은 레이아웃\n"
        "2) 헤더: 제목/일시/작성자만 표시 (수신/참조/진척관리/기타 근태 섹션 금지)\n"
        "3) 본문 표는 3열: 구분 | 실적(기간표기) | 계획(기간표기)\n"
        "4) 구분 행은 정확히 '주요 진행 상황', '이슈', 'Action Item'\n"
        "5) 실적/계획은 각 셀 내 불릿 목록으로 3~6개 작성\n"
        "5-1) 각 불릿은 반드시 2줄 형식으로 작성: 첫 줄은 핵심 항목, 둘째 줄은 '- '로 시작하는 설명\n"
        "     예: <li>API 호출 상태 점검<br>- 장애 징후와 재발 방지 관점에서 확인 범위를 명시</li>\n"
        "6) Action Item은 담당자/기한/조치내용 형식으로 작성\n"
        "7) 문체는 업무용 간결체, 과장 금지, 근거 없는 제품명/조직명/연도 생성 금지\n"
        "8) 모든 날짜는 입력된 기간/오늘 날짜 기준으로만 작성\n"
        "9) CSS 포함: max-width 1360px, 폰트 Malgun Gothic, 표 헤더 #1f4e79 흰 글자"
    )
    return [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_prompt},
    ]


def _extract_weekly_detail_from_text(text: str) -> str:
    """
    주간보고 불릿 본문에서 하위 설명 문장을 생성한다.

    Args:
        text: 불릿 원문 텍스트

    Returns:
        '- ' 뒤에 붙일 설명 문장
    """
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if not normalized:
        return "근거 메일 기준으로 세부 내용을 확인합니다."
    if " / " in normalized:
        parts = [part.strip() for part in normalized.split("/") if part.strip()]
        if len(parts) >= 3:
            return f"담당: {parts[0]}, 일정: {parts[1]} 기준으로 {parts[2]}를 진행합니다."
        if len(parts) == 2:
            return f"{parts[1]} 기준으로 후속 조치를 진행합니다."
    if ":" in normalized:
        head, tail = normalized.split(":", 1)
        if tail.strip():
            return f"{head.strip()} 기준 세부 항목: {tail.strip()}"
    return "근거 메일 기준으로 배경/영향/후속 조치를 함께 확인합니다."


def _ensure_weekly_bullet_sublines(html_text: str) -> str:
    """
    주간보고 HTML의 각 불릿에 '- ' 설명 줄을 보강한다.

    Args:
        html_text: 모델이 생성한 주간보고 HTML

    Returns:
        하위 설명 줄이 보강된 HTML
    """
    source = str(html_text or "")
    if not source:
        return ""
    li_pattern = re.compile(r"(<li\b[^>]*>)(.*?)(</li>)", flags=re.IGNORECASE | re.DOTALL)

    def _replace(match: re.Match[str]) -> str:
        opening, body, closing = match.group(1), match.group(2), match.group(3)
        if re.search(r"<br\s*/?>\s*-\s*", body, flags=re.IGNORECASE):
            return f"{opening}{body}{closing}"
        plain = re.sub(r"<[^>]+>", " ", body)
        detail = _extract_weekly_detail_from_text(html.unescape(plain))
        return f"{opening}{body}<br>- {html.escape(detail)}{closing}"

    return li_pattern.sub(_replace, source)


def generate_report_html_fast(
    email_subject: str,
    email_content: str,
    report_date: str,
    report_author: str,
) -> str:
    """
    단일 모델 호출로 현재 메일 기반 보고서 HTML을 생성한다.

    Args:
        email_subject: 보고서 제목(메일 제목)
        email_content: 보고서 작성 근거 원문
        report_date: 표지 날짜(일반적으로 현재 날짜)
        report_author: 작성자 이름/조직

    Returns:
        생성된 HTML 문자열(실패 시 빈 문자열)
    """
    model_name = normalize_azure_deployment_name(
        model_name=str(os.getenv("SUMMARIZATION_MODEL", DEFAULT_REPORT_MODEL)).strip(),
        default_deployment=DEFAULT_REPORT_MODEL,
    )
    messages = _build_fast_report_messages(
        email_subject=email_subject,
        email_content=email_content,
        report_date=report_date,
        report_author=report_author,
    )
    try:
        completion = _get_azure_openai_client().chat.completions.create(model=model_name, messages=messages)
    except OpenAIError as exc:
        logger.warning("report_agent.fast_path_failed: %s", exc)
        return ""
    content = str(completion.choices[0].message.content or "").strip()
    normalized = _strip_code_fence(content)
    logger.info(
        "report_agent.fast_path_completed: model=%s input_length=%s html_length=%s",
        model_name,
        len(str(email_content or "")),
        len(normalized),
    )
    return normalized


def generate_weekly_report_html_fast(
    mail_items: list[dict[str, str]],
    week_offset: int,
    report_author: str,
    reference_date: str = "",
) -> str:
    """
    단일 모델 호출로 주간보고 HTML을 생성한다.

    Args:
        mail_items: 실적 기간 메일 목록
        week_offset: 몇 주 전 기준인지 나타내는 오프셋
        report_author: 보고서 작성자
        reference_date: 기준일

    Returns:
        생성된 HTML 문자열(실패 시 빈 문자열)
    """
    model_name = normalize_azure_deployment_name(
        model_name=str(os.getenv("SUMMARIZATION_MODEL", DEFAULT_REPORT_MODEL)).strip(),
        default_deployment=DEFAULT_REPORT_MODEL,
    )
    messages = _build_weekly_report_messages(
        mail_items=mail_items,
        week_offset=week_offset,
        report_author=report_author,
        reference_date=reference_date,
    )
    try:
        completion = _get_azure_openai_client().chat.completions.create(model=model_name, messages=messages)
    except OpenAIError as exc:
        logger.warning("weekly_report_agent.fast_path_failed: %s", exc)
        return ""
    content = str(completion.choices[0].message.content or "").strip()
    normalized = _ensure_weekly_bullet_sublines(_strip_code_fence(content))
    logger.info(
        "weekly_report_agent.fast_path_completed: model=%s items=%s html_length=%s",
        model_name,
        len(mail_items),
        len(normalized),
    )
    return normalized
