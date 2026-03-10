from __future__ import annotations

import html
import re
from datetime import datetime
from typing import Any
from urllib.parse import quote


def normalize_mail_search_summary_text(value: object) -> str:
    """
    mail_search 단건 summary_text를 단일 라인으로 정규화한다.

    Args:
        value: summary_text 원본 값

    Returns:
        정규화된 summary 텍스트
    """
    text = _strip_html_noise(text=str(value or ""))
    text = re.sub(r"\s+", " ", text).strip()
    text = re.sub(r"^[\-\*•\d\)\.\s]+", "", text).strip()
    if len(text) > 160:
        return text[:159].rstrip() + "…"
    return text


def resolve_mail_search_summary_from_db(item: dict[str, Any]) -> str:
    """
    mail_search 결과 항목에서 DB summary_text만 사용해 요약 문자열을 반환한다.

    Args:
        item: mail_search 결과 항목

    Returns:
        정규화된 summary 텍스트(없으면 빈 문자열)
    """
    return normalize_mail_search_summary_text(item.get("summary_text"))


def _strip_html_noise(text: str) -> str:
    """
    HTML 엔티티/태그가 포함된 요약 문자열을 사람이 읽기 쉬운 텍스트로 정리한다.

    Args:
        text: 원본 문자열

    Returns:
        정리된 평문 문자열
    """
    normalized = html.unescape(str(text or ""))
    email_placeholders: dict[str, str] = {}
    matches = re.findall(r"<([A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,})>", normalized)
    for index, match in enumerate(matches):
        token = f"__EMAIL_TOKEN_{index}__"
        email_placeholders[token] = match
        normalized = normalized.replace(f"<{match}>", token)
    normalized = normalized.replace("\xa0", " ")
    normalized = re.sub(r"<br\s*/?>", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"</p\s*>", " ", normalized, flags=re.IGNORECASE)
    normalized = re.sub(r"<[^>]+>", " ", normalized)
    for token, email_value in email_placeholders.items():
        normalized = normalized.replace(token, email_value)
    return normalized


def build_markdown_link(text: str, url: str, message_id: str = "") -> str:
    """
    제목/링크로 markdown 링크 문자열을 생성한다.

    Args:
        text: 링크 텍스트
        url: 링크 URL
        message_id: Outlook message id

    Returns:
        markdown 링크 문자열
    """
    safe_text = str(text or "").replace("[", "\\[").replace("]", "\\]")
    safe_url = str(url or "").strip()
    normalized_message_id = str(message_id or "").strip()
    if normalized_message_id:
        encoded_mid = quote(normalized_message_id, safe="")
        separator = "&" if "?" in safe_url else "?"
        safe_url = f"{safe_url}{separator}moldubot_mid={encoded_mid}"
    return f"[{safe_text}]({safe_url})"


def normalize_received_date(value: object) -> str:
    """
    수신일 텍스트를 YYYY-MM-DD 형식으로 정규화한다.

    Args:
        value: 원본 수신일 문자열

    Returns:
        정규화 날짜 문자열
    """
    text = str(value or "").strip()
    if not text:
        return "-"
    matched = re.match(r"^(\d{4}-\d{2}-\d{2})", text)
    if matched:
        return matched.group(1)
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
        return parsed.strftime("%Y-%m-%d")
    except ValueError:
        return text


def extract_requested_mail_count(user_message: str) -> int:
    """
    사용자 문장에서 요청한 메일 개수를 추출한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        요청 개수. 미추출 시 0
    """
    matched = re.search(r"(\d{1,2})\s*개", str(user_message or ""))
    if not matched:
        return 0
    return max(1, int(matched.group(1)))


def sort_results_by_received_date_desc(results: list[Any]) -> list[dict[str, Any]]:
    """
    검색 결과를 received_date 기준 내림차순으로 정렬한다.

    Args:
        results: 원본 results 목록

    Returns:
        정렬된 결과 목록(dict만 유지)
    """
    normalized_results = [item for item in results if isinstance(item, dict)]
    return sorted(normalized_results, key=received_date_sort_key, reverse=True)


def received_date_sort_key(item: dict[str, Any]) -> datetime:
    """
    단일 결과 항목의 received_date를 정렬 키(datetime)로 변환한다.

    Args:
        item: 검색 결과 항목

    Returns:
        파싱된 datetime. 실패 시 최소값
    """
    raw = str(item.get("received_date") or "").strip()
    if not raw:
        return datetime.min
    iso_candidate = raw.replace("Z", "+00:00")
    for pattern in ("%Y-%m-%d", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(iso_candidate, pattern)
        except ValueError:
            continue
    try:
        return datetime.fromisoformat(iso_candidate)
    except ValueError:
        return datetime.min


def is_mail_search_summary_request(user_message: str) -> bool:
    """
    메일 검색 요약 질의 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        메일 검색 요약 질의면 True
    """
    text = str(user_message or "")
    if "메일" not in text:
        return False
    has_search = ("조회" in text) or ("검색" in text) or ("찾" in text)
    has_summary = ("요약" in text) or ("정리" in text)
    return has_search and has_summary


def is_recent_sorted_mail_request(user_message: str) -> bool:
    """
    최근순 목록 정리 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        최근순 목록 요청이면 True
    """
    text = str(user_message or "").strip()
    if "메일" not in text:
        return False
    has_recent_sort = ("최근순" in text) or ("최신순" in text)
    has_list_intent = ("정리" in text) or ("목록" in text) or ("보여" in text) or ("조회" in text)
    return has_recent_sort and has_list_intent


def is_mail_search_action_with_results(tool_payload: dict[str, Any]) -> bool:
    """
    tool payload가 결과를 포함한 mail_search 응답인지 판별한다.

    Args:
        tool_payload: 직전 tool payload

    Returns:
        결과가 있는 mail_search 응답이면 True
    """
    action = str(tool_payload.get("action") or "").strip().lower()
    if action != "mail_search":
        return False
    results = tool_payload.get("results")
    return isinstance(results, list) and len(results) > 0


def has_structured_summary_header(answer: str) -> bool:
    """
    응답 본문이 이미 구조화된 요약 헤더를 포함하는지 검사한다.

    Args:
        answer: 모델 응답 텍스트

    Returns:
        구조화 헤더가 있으면 True
    """
    text = str(answer or "").strip()
    if not text:
        return False
    structured_markers = ("요약 결과:", "주요 내용:", "## 📌 주요 내용", "\n- ", "\n1. ")
    return any(marker in text for marker in structured_markers)


def extract_mail_search_overview_lines(answer: str, tool_payload: dict[str, Any]) -> list[str]:
    """
    조회 응답 상단 요약 후보 라인을 payload/answer에서 추출한다.

    Args:
        answer: 모델 응답 텍스트
        tool_payload: 직전 tool payload

    Returns:
        요약 라인 목록
    """
    del answer
    aggregated = tool_payload.get("aggregated_summary")
    if not isinstance(aggregated, list):
        return []
    lines = [str(item).strip() for item in aggregated if str(item or "").strip()]
    return lines[:5]


def is_mail_search_no_result(user_message: str, tool_payload: dict[str, Any]) -> bool:
    """
    메일 검색 요약 질의에서 검색 결과 0건 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문
        tool_payload: 직전 tool payload

    Returns:
        mail_search 결과가 0건이면 True
    """
    if "메일" not in str(user_message or ""):
        return False
    action = str(tool_payload.get("action") or "").strip().lower()
    if action != "mail_search":
        return False
    status = str(tool_payload.get("status") or "").strip().lower()
    if status and status != "completed":
        return False
    reason = str(tool_payload.get("reason") or "").strip()
    if "현재메일 범위" in reason:
        return False
    results = tool_payload.get("results")
    if isinstance(results, list):
        return len(results) == 0
    count = tool_payload.get("count")
    if isinstance(count, int):
        return count == 0
    return False


def render_mail_search_no_result_message(user_message: str) -> str:
    """
    mail_search 결과가 0건일 때 표준 안내 메시지를 생성한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        0건 안내 응답 문자열
    """
    lines = [
        "조회 결과: 조건에 맞는 메일이 없습니다.",
        "다음 제안: 기간 또는 키워드를 조정해 다시 조회해 주세요.",
    ]
    text = str(user_message or "")
    if ("todo" in text.lower()) or ("액션" in text) or ("조치" in text):
        lines.extend(
            [
                "",
                "### 임시 TODO",
                "1. 검색 기간을 재확인합니다.",
                "2. 검색 키워드(사람명/프로젝트명)를 구체화합니다.",
                "3. 재조회 후 TODO를 확정합니다.",
            ]
        )
    if "표" in text:
        lines.extend(["", "| 항목 | 값 |", "|---|---|", "| 조회 건수 | 0 |", "| 비고 | 조건에 맞는 메일 없음 |"])
    return "\n".join(lines).strip()
