from __future__ import annotations

from typing import Any, Mapping

from app.services.answer_postprocessor_mail_search_digest import (
    collect_mail_search_digest_lines,
    render_mail_search_digest_from_db,
)
from app.services.answer_postprocessor_mail_search_utils import (
    build_markdown_link,
    extract_mail_search_overview_lines,
    extract_requested_mail_count,
    has_structured_summary_header,
    is_mail_search_action_with_results,
    is_mail_search_no_result,
    is_mail_search_summary_request,
    is_recent_sorted_mail_request,
    normalize_mail_search_summary_text,
    normalize_received_date,
    render_mail_search_no_result_message,
    resolve_mail_search_summary_from_db,
    sort_results_by_received_date_desc,
)
from app.services.answer_postprocessor_summary import render_mail_search_summary_lines

__all__ = [
    "collect_mail_search_digest_lines",
    "is_mail_search_no_result",
    "normalize_mail_search_summary_text",
    "render_mail_search_deterministic_response",
    "render_mail_search_no_result_message",
    "render_mail_search_overview_summary",
    "render_mail_search_result_items",
    "render_recent_sorted_mail_response",
]


def render_mail_search_overview_summary(user_message: str, answer: str, tool_payload: dict[str, Any]) -> str:
    """
    메일 조회 응답의 상단 요약을 제목+불릿 형식으로 정규화한다.

    Args:
        user_message: 사용자 입력 원문
        answer: 모델 응답 텍스트
        tool_payload: 직전 tool payload

    Returns:
        렌더링 결과 문자열. 조건 불충족 시 빈 문자열
    """
    if not is_mail_search_summary_request(user_message=user_message):
        return ""
    if not is_mail_search_action_with_results(tool_payload=tool_payload):
        return ""

    rendered_by_results = render_mail_search_overview_from_results(tool_payload=tool_payload)
    if rendered_by_results:
        return rendered_by_results
    if has_structured_summary_header(answer=answer):
        return ""

    summary_lines = extract_mail_search_overview_lines(answer=answer, tool_payload=tool_payload)
    if not summary_lines:
        return ""
    return render_mail_search_summary_lines(lines=summary_lines)


def render_mail_search_overview_from_results(tool_payload: dict[str, Any]) -> str:
    """
    mail_search 결과를 메일 단위(제목 링크 + DB summary)로 렌더링한다.

    Args:
        tool_payload: 직전 tool payload

    Returns:
        주요 내용 렌더링 문자열
    """
    results = tool_payload.get("results")
    if not isinstance(results, list) or not results:
        return ""

    lines = ["## 📌 주요 내용"]
    item_count = 0
    for raw_item in results:
        if not isinstance(raw_item, dict):
            continue
        subject = str(raw_item.get("subject") or "제목 없음").strip() or "제목 없음"
        summary_text = normalize_mail_search_summary_text(raw_item.get("summary_text"))
        web_link = str(raw_item.get("web_link") or "").strip()
        message_id = str(raw_item.get("message_id") or "").strip()
        title_text = build_markdown_link(text=subject, url=web_link, message_id=message_id) if web_link else subject
        item_count += 1
        lines.append(f"{item_count}. {title_text}")
        lines.append(f"- {summary_text or '저장된 요약이 없습니다.'}")

    if item_count == 0:
        return ""
    return "\n".join(lines).strip()


def render_mail_search_deterministic_response(
    user_message: str,
    tool_payload: dict[str, Any],
    section_contract: Mapping[str, object] | None = None,
) -> str:
    """
    mail_search 결과를 LLM 자유서술 없이 결과 레코드 기반으로 고정 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        tool_payload: 직전 tool payload
        section_contract: 섹션 계약 정보

    Returns:
        고정 포맷 응답. 조건 불충족 시 빈 문자열
    """
    action = str(tool_payload.get("action") or "").strip().lower()
    if action != "mail_search":
        return ""

    if not _is_mail_search_listing_request(user_message=user_message):
        return ""

    has_query_summaries = isinstance(tool_payload.get("query_summaries"), list) and bool(tool_payload.get("query_summaries"))
    if is_mail_search_summary_request(user_message=user_message) and has_query_summaries:
        digest_rendered = render_mail_search_digest_from_db(
            tool_payload=tool_payload,
            line_target=3,
            section_contract=section_contract,
        )
        if digest_rendered:
            return digest_rendered

    results = tool_payload.get("results")
    if not isinstance(results, list) or not results:
        return ""

    if is_mail_search_summary_request(user_message=user_message):
        digest_rendered = render_mail_search_digest_from_db(
            tool_payload=tool_payload,
            line_target=3,
            section_contract=section_contract,
        )
        if digest_rendered:
            return digest_rendered
    return render_mail_search_result_items(user_message=user_message, results=results)


def _is_mail_search_listing_request(user_message: str) -> bool:
    """
    메일 검색 결과를 목록형으로 강제 렌더링해도 되는 조회성 질의인지 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        목록형 조회 질의면 True
    """
    normalized = str(user_message or "").strip()
    if "메일" not in normalized:
        return False
    listing_tokens = ("조회", "검색", "찾아", "목록", "보여", "최근순", "최신순")
    return any(token in normalized for token in listing_tokens)


def render_mail_search_result_items(user_message: str, results: list[dict[str, Any]]) -> str:
    """
    mail_search 결과를 목록/표 형태로 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        results: 조회된 메일 결과 목록

    Returns:
        렌더링 문자열
    """
    normalized_results = sort_results_by_received_date_desc(results=results)
    requested_count = extract_requested_mail_count(user_message=user_message)
    target_count = min(len(normalized_results), requested_count if requested_count > 0 else 5)
    selected_results = normalized_results[:target_count]

    if "표" in str(user_message or ""):
        return _render_mail_search_result_table(selected_results=selected_results)
    return _render_mail_search_result_list(selected_results=selected_results)


def _render_mail_search_result_table(selected_results: list[dict[str, Any]]) -> str:
    """
    메일 검색 결과를 표 형태로 렌더링한다.

    Args:
        selected_results: 정렬/컷오프가 완료된 결과 목록

    Returns:
        표 렌더링 결과 문자열
    """
    table_lines = ["## 📌 주요 내용", "", "| 메일 제목 | 발신자 | 수신일 | 요약 |", "|---|---|---|---|"]
    for item in selected_results:
        subject = str(item.get("subject") or "제목 없음").strip() or "제목 없음"
        sender = str(item.get("sender_names") or item.get("from_address") or "-").strip() or "-"
        received_date = normalize_received_date(item.get("received_date"))
        summary = resolve_mail_search_summary_from_db(item)
        table_lines.append(f"| {subject} | {sender} | {received_date} | {summary or '-'} |")
    return "\n".join(table_lines).strip()


def _render_mail_search_result_list(selected_results: list[dict[str, Any]]) -> str:
    """
    메일 검색 결과를 목록 형태로 렌더링한다.

    Args:
        selected_results: 정렬/컷오프가 완료된 결과 목록

    Returns:
        목록 렌더링 결과 문자열
    """
    lines = ["## 📌 주요 내용"]
    for index, item in enumerate(selected_results, start=1):
        subject = str(item.get("subject") or "제목 없음").strip() or "제목 없음"
        sender = str(item.get("sender_names") or item.get("from_address") or "-").strip() or "-"
        received_date = normalize_received_date(item.get("received_date"))
        summary = resolve_mail_search_summary_from_db(item)
        web_link = str(item.get("web_link") or "").strip()
        message_id = str(item.get("message_id") or "").strip()
        title = build_markdown_link(text=subject, url=web_link, message_id=message_id) if web_link else subject
        lines.append(f"{index}. {title}")
        lines.append(f"- 요약: {summary or '저장된 요약이 없습니다.'}")
        lines.append(f"- 보낸 사람: {sender}")
        lines.append(f"- 수신일: {received_date}")
    return "\n".join(lines).strip()


def render_recent_sorted_mail_response(user_message: str, tool_payload: dict[str, Any]) -> str:
    """
    `최근순/최신순` 조회 요청은 결과 목록을 날짜 포함 고정 포맷으로 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        tool_payload: 직전 tool payload

    Returns:
        렌더링된 텍스트. 조건 불충족 시 빈 문자열
    """
    if not is_recent_sorted_mail_request(user_message=user_message):
        return ""
    action = str(tool_payload.get("action") or "").strip().lower()
    if action != "mail_search":
        return ""
    results = tool_payload.get("results")
    if not isinstance(results, list) or not results:
        return ""

    normalized_results = sort_results_by_received_date_desc(results=results)
    requested_count = extract_requested_mail_count(user_message=user_message)
    available_count = len(normalized_results)
    target_count = min(available_count, requested_count if requested_count > 0 else 5)

    lines = [
        "## 📌 주요 내용",
        "최근순 메일 " + str(target_count) + "건 정리 결과:",
        f"- (조회 결과 기준 총 {available_count}건 중 {target_count}건)",
    ]
    for index, item in enumerate(normalized_results[:target_count], start=1):
        if not isinstance(item, dict):
            continue
        received_date = normalize_received_date(item.get("received_date"))
        subject = str(item.get("subject") or "제목 없음").strip() or "제목 없음"
        sender = str(item.get("sender_names") or item.get("from_address") or "-").strip() or "-"
        web_link = str(item.get("web_link") or "").strip()
        message_id = str(item.get("message_id") or "").strip()
        title_text = build_markdown_link(text=subject, url=web_link, message_id=message_id) if web_link else subject
        lines.append(f"{index}. [{received_date}] {title_text} ({sender})")
        lines.append(f"- 보낸 사람: {sender}")
    return "\n".join(lines).strip()
