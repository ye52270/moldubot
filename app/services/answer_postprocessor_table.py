from __future__ import annotations

from app.models.response_contracts import LLMResponseContract
from app.services.answer_postprocessor_summary import sanitize_summary_lines
from app.services.answer_table_spec_utils import render_markdown_table

TABLE_REQUEST_TOKENS: tuple[str, ...] = ("표", "테이블", "table")
TABLE_EXCLUDE_TOKENS: tuple[str, ...] = ("차트", "그래프", "graph", "plot")
MAX_GENERIC_TABLE_ROWS = 12


def is_generic_table_request(user_message: str) -> bool:
    """
    일반 표 렌더가 필요한 사용자 요청인지 판별한다.

    Args:
        user_message: 정규화 사용자 입력

    Returns:
        일반 표 요청이면 True
    """
    text = str(user_message or "").strip().lower()
    if not text:
        return False
    if any(token in text for token in TABLE_EXCLUDE_TOKENS):
        return False
    return any(token in text for token in TABLE_REQUEST_TOKENS)


def render_generic_table_from_contract(user_message: str, contract: LLMResponseContract) -> str:
    """
    일반 표 요청에 대해 계약 필드를 markdown 표로 결정론 렌더링한다.

    Args:
        user_message: 정규화 사용자 입력
        contract: 파싱된 LLM 응답 계약

    Returns:
        렌더링 결과. 적용 대상이 아니면 빈 문자열
    """
    if not is_generic_table_request(user_message=user_message):
        return ""
    rows = _build_rows_from_contract(contract=contract)
    if not rows:
        return ""
    title = "## 표 정리"
    headers = ["구분", "내용"]
    return render_markdown_table(
        title=title,
        headers=headers,
        rows=rows[:MAX_GENERIC_TABLE_ROWS],
        empty_message="표로 정리할 항목을 찾지 못했습니다.",
    )


def _build_rows_from_contract(contract: LLMResponseContract) -> list[list[str]]:
    """
    계약 필드를 표 행 목록으로 변환한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        표 행 목록([구분, 내용])
    """
    rows: list[list[str]] = []
    if str(contract.one_line_summary or "").strip():
        rows.append(["한줄요약", str(contract.one_line_summary).strip()])
    if str(contract.core_issue or "").strip():
        rows.append(["핵심이슈", str(contract.core_issue).strip()])
    for line in sanitize_summary_lines(lines=list(contract.summary_lines)):
        rows.append(["요약", line])
    for line in sanitize_summary_lines(lines=list(contract.major_points)):
        rows.append(["주요내용", line])
    for line in sanitize_summary_lines(lines=list(contract.required_actions)):
        rows.append(["조치", line])
    for line in sanitize_summary_lines(lines=list(contract.action_items)):
        rows.append(["액션", line])
    return _dedupe_rows(rows=rows)


def _dedupe_rows(rows: list[list[str]]) -> list[list[str]]:
    """
    동일 행(구분+내용) 중복을 제거한다.

    Args:
        rows: 원본 행 목록

    Returns:
        중복 제거된 행 목록
    """
    deduped: list[list[str]] = []
    seen: set[str] = set()
    for row in rows:
        if len(row) < 2:
            continue
        category = str(row[0] or "").strip()
        text = str(row[1] or "").strip()
        if not category or not text:
            continue
        key = f"{category.lower()}::{text.lower()}"
        if key in seen:
            continue
        seen.add(key)
        deduped.append([category, text])
    return deduped
