from __future__ import annotations

import re
from typing import Any

from app.agents.intent_schema import ExecutionStep, IntentDecomposition, IntentOutputFormat, IntentTaskType
MAX_BLOCKS = 64
def build_answer_format_metadata(
    user_message: str,
    answer: str,
    status: str = "completed",
    decomposition: IntentDecomposition | None = None,
) -> dict[str, Any]:
    """
    최종 응답 텍스트를 UI 친화적 블록 메타데이터로 변환한다.

    Args:
        user_message: 사용자 입력 원문
        answer: 최종 사용자 노출 응답 텍스트
        status: API 응답 상태값
        decomposition: 구조화 의도 결과(있으면 format 추론에 우선 사용)

    Returns:
        version/format_type/blocks를 포함한 포맷 메타데이터
    """
    _ = user_message
    normalized_answer = _normalize_text(text=answer)
    format_type = _infer_format_type(
        answer=normalized_answer,
        status=status,
        decomposition=decomposition,
    )
    blocks = _extract_blocks(text=normalized_answer)
    return {
        "version": "v1",
        "format_type": format_type,
        "blocks": blocks,
    }
def _normalize_text(text: str) -> str:
    """
    개행/공백을 정규화한다.

    Args:
        text: 원문 문자열

    Returns:
        정규화된 문자열
    """
    normalized = str(text or "").replace("\r\n", "\n").strip()
    normalized = _insert_structural_newlines(text=normalized)
    return normalized.strip()


def _insert_structural_newlines(text: str) -> str:
    """
    마크다운 구조 토큰 주변에 개행을 보강해 블록 파싱 안정성을 높인다.

    Args:
        text: 정규화 전 텍스트

    Returns:
        개행 보강된 텍스트
    """
    if not text:
        return ""
    normalized = str(text)
    normalized = re.sub(r"(?<!\n)---(?=#{1,6}\s*)", r"---\n", normalized)
    normalized = re.sub(r"(?<![\n#])(?=#{1,6}\s+)", "\n", normalized)
    return normalized


def _infer_format_type(
    answer: str,
    status: str,
    decomposition: IntentDecomposition | None = None,
) -> str:
    """
    사용자 질의와 응답 텍스트 패턴으로 format_type을 추론한다.

    Args:
        answer: 정규화된 응답 텍스트
        status: API 응답 상태
        decomposition: 구조화 의도 결과

    Returns:
        추론된 포맷 타입
    """
    if status == "needs_clarification":
        return "clarification_card"
    if decomposition is not None:
        has_current_mail_context = ExecutionStep.READ_CURRENT_MAIL in decomposition.steps
        if has_current_mail_context and decomposition.output_format == IntentOutputFormat.TRANSLATION:
            return "current_mail_translation"
        if has_current_mail_context:
            return "current_mail"
        if decomposition.task_type == IntentTaskType.SUMMARY:
            return "summary"
    if "근거메일" in answer:
        return "grounded_answer"
    return "general"


def _extract_blocks(text: str) -> list[dict[str, Any]]:
    """
    마크다운 유사 텍스트를 블록 목록으로 분해한다.

    Args:
        text: 정규화된 텍스트

    Returns:
        블록 메타데이터 목록
    """
    if not text:
        return [{"type": "paragraph", "text": ""}]
    lines = text.split("\n")
    blocks: list[dict[str, Any]] = []
    index = 0
    while index < len(lines):
        line = str(lines[index] or "").strip()
        if not line:
            index += 1
            continue
        heading_match = re.match(r"^(#{1,6})\s+(.+)$", line)
        if heading_match:
            blocks.append(
                {
                    "type": "heading",
                    "level": len(heading_match.group(1)),
                    "text": heading_match.group(2).strip(),
                }
            )
            index += 1
            continue
        if _is_quote_line(line=line):
            quote_text, next_index = _collect_quote(lines=lines, start=index)
            blocks.append({"type": "quote", "text": quote_text})
            index = next_index
            continue
        next_line = str(lines[index + 1] or "").strip() if (index + 1) < len(lines) else ""
        if _is_table_header_candidate(line=line, next_line=next_line):
            table_block, next_index = _collect_table(lines=lines, start=index)
            blocks.append(table_block)
            index = next_index
            continue
        if _is_ordered_list_line(line=line):
            list_items, next_index = _collect_list_items(lines=lines, start=index, ordered=True)
            blocks.append({"type": "ordered_list", "items": list_items})
            index = next_index
            continue
        if _is_unordered_list_line(line=line):
            list_items, next_index = _collect_list_items(lines=lines, start=index, ordered=False)
            blocks.append({"type": "unordered_list", "items": list_items})
            index = next_index
            continue
        paragraph, next_index = _collect_paragraph(lines=lines, start=index)
        blocks.append({"type": "paragraph", "text": paragraph})
        index = next_index
    return _truncate_blocks(blocks=blocks, max_blocks=MAX_BLOCKS)


def _truncate_blocks(blocks: list[dict[str, Any]], max_blocks: int) -> list[dict[str, Any]]:
    """
    블록 목록을 상한 길이로 제한하되 핵심 섹션 짝(헤딩+목록)을 보존한다.

    Args:
        blocks: 원본 블록 목록
        max_blocks: 최대 블록 수

    Returns:
        상한이 적용된 블록 목록
    """
    if max_blocks <= 0:
        return []
    if len(blocks) <= max_blocks:
        return blocks
    trimmed = list(blocks[:max_blocks])
    action_heading_index = _find_action_heading_index(blocks=trimmed)
    if action_heading_index < 0:
        return trimmed
    if action_heading_index + 1 < len(trimmed) and _is_list_block(block=trimmed[action_heading_index + 1]):
        return trimmed
    action_list_block = _find_next_action_list_block(blocks=blocks, start_index=action_heading_index + 1)
    if action_list_block is None:
        return trimmed
    if action_heading_index >= len(trimmed) - 1:
        replace_index = _find_replace_index_before_heading(
            trimmed=trimmed,
            action_heading_index=action_heading_index,
        )
        if replace_index < 0:
            return trimmed
        del trimmed[replace_index]
        if replace_index < action_heading_index:
            action_heading_index -= 1
        trimmed.insert(action_heading_index + 1, action_list_block)
        return trimmed[:max_blocks]
    trimmed[action_heading_index + 1] = action_list_block
    return trimmed


def _find_action_heading_index(blocks: list[dict[str, Any]]) -> int:
    """
    블록 목록에서 조치 섹션 헤딩 인덱스를 찾는다.

    Args:
        blocks: 블록 목록

    Returns:
        헤딩 인덱스. 없으면 -1
    """
    for index, block in enumerate(blocks):
        if str(block.get("type") or "").strip() != "heading":
            continue
        heading_text = str(block.get("text") or "")
        if _is_action_heading_text(text=heading_text):
            return index
    return -1


def _find_next_action_list_block(blocks: list[dict[str, Any]], start_index: int) -> dict[str, Any] | None:
    """
    조치 헤딩 이후의 첫 목록 블록을 찾는다.

    Args:
        blocks: 전체 블록 목록
        start_index: 검색 시작 인덱스

    Returns:
        목록 블록 또는 None
    """
    index = max(0, start_index)
    while index < len(blocks):
        block = blocks[index]
        if _is_list_block(block=block):
            items = block.get("items")
            if isinstance(items, list) and items:
                return block
        if str(block.get("type") or "").strip() == "heading":
            break
        index += 1
    return None


def _find_replace_index_before_heading(trimmed: list[dict[str, Any]], action_heading_index: int) -> int:
    """
    조치 헤딩 이전 구간에서 교체 가능한 블록 인덱스를 찾는다.

    Args:
        trimmed: 길이 제한이 적용된 블록 목록
        action_heading_index: 조치 헤딩 인덱스

    Returns:
        교체 인덱스. 없으면 -1
    """
    for index in range(action_heading_index - 1, -1, -1):
        block = trimmed[index]
        if str(block.get("type") or "").strip() == "heading" and _is_action_heading_text(text=str(block.get("text") or "")):
            continue
        return index
    return -1


def _is_action_heading_text(text: str) -> bool:
    """
    헤딩 텍스트가 조치 섹션인지 판별한다.

    Args:
        text: 헤딩 텍스트

    Returns:
        조치 필요 섹션이면 True
    """
    compact = re.sub(r"\s+", "", str(text or "")).lower()
    return ("조치필요" in compact) or ("필요조치" in compact)


def _is_list_block(block: dict[str, Any]) -> bool:
    """
    블록이 목록 타입인지 판별한다.

    Args:
        block: 블록 dict

    Returns:
        목록 블록이면 True
    """
    block_type = str(block.get("type") or "").strip()
    return block_type in {"ordered_list", "unordered_list"}


def _is_ordered_list_line(line: str) -> bool:
    """
    번호 목록 라인 여부를 판별한다.

    Args:
        line: 검사 대상 라인

    Returns:
        번호 목록이면 True
    """
    return bool(re.match(r"^\d+\.\s+", line))


def _is_unordered_list_line(line: str) -> bool:
    """
    불릿 목록 라인 여부를 판별한다.

    Args:
        line: 검사 대상 라인

    Returns:
        불릿 목록이면 True
    """
    return bool(re.match(r"^[-*•]\s+", line))


def _is_quote_line(line: str) -> bool:
    """
    인용문 라인 여부를 판별한다.

    Args:
        line: 검사 대상 라인

    Returns:
        인용문이면 True
    """
    return bool(re.match(r"^>\s*", line))


def _is_table_header_candidate(line: str, next_line: str) -> bool:
    """
    markdown table 헤더 시작 여부를 판별한다.

    Args:
        line: 현재 라인
        next_line: 다음 라인

    Returns:
        table 헤더 후보면 True
    """
    if "|" not in line:
        return False
    if _is_table_delimiter_line(line=line):
        return False
    compact = str(next_line or "").replace("|", "").strip()
    if not compact:
        return False
    return bool(re.match(r"^[:\- ]+$", compact))


def _collect_list_items(lines: list[str], start: int, ordered: bool) -> tuple[list[str], int]:
    """
    연속된 목록 라인을 수집한다.

    Args:
        lines: 전체 라인 배열
        start: 시작 인덱스
        ordered: 번호 목록 여부

    Returns:
        (수집 목록, 다음 인덱스)
    """
    items: list[str] = []
    index = start
    while index < len(lines):
        line = str(lines[index] or "").strip()
        if not line:
            break
        is_target = _is_ordered_list_line(line=line) if ordered else _is_unordered_list_line(line=line)
        if not is_target:
            break
        item_text = re.sub(r"^\d+\.\s+|^[-*•]\s+", "", line).strip()
        if item_text:
            items.append(item_text)
        index += 1
    return items, index


def _collect_paragraph(lines: list[str], start: int) -> tuple[str, int]:
    """
    다음 블록 경계(빈줄/리스트/헤딩) 전까지 문단을 수집한다.

    Args:
        lines: 전체 라인 배열
        start: 시작 인덱스

    Returns:
        (문단 텍스트, 다음 인덱스)
    """
    parts: list[str] = []
    index = start
    while index < len(lines):
        line = str(lines[index] or "").strip()
        if not line:
            break
        if re.match(r"^(#{1,6})\s+.+$", line):
            break
        if _is_quote_line(line=line):
            break
        if _is_ordered_list_line(line=line) or _is_unordered_list_line(line=line):
            break
        next_line = str(lines[index + 1] or "").strip() if (index + 1) < len(lines) else ""
        if _is_table_header_candidate(line=line, next_line=next_line):
            break
        parts.append(line)
        index += 1
    return " ".join(parts).strip(), index


def _collect_quote(lines: list[str], start: int) -> tuple[str, int]:
    """
    연속된 인용문 라인을 수집한다.

    Args:
        lines: 전체 라인 배열
        start: 시작 인덱스

    Returns:
        (인용문 텍스트, 다음 인덱스)
    """
    parts: list[str] = []
    index = start
    while index < len(lines):
        line = str(lines[index] or "").strip()
        if not line or not _is_quote_line(line=line):
            break
        parts.append(re.sub(r"^>\s*", "", line).strip())
        index += 1
    return " ".join([part for part in parts if part]).strip(), index


def _collect_table(lines: list[str], start: int) -> tuple[dict[str, Any], int]:
    """
    markdown table 블록을 수집한다.

    Args:
        lines: 전체 라인 배열
        start: 시작 인덱스

    Returns:
        ({type, headers, rows}, 다음 인덱스)
    """
    header_line = str(lines[start] or "").strip()
    headers = _split_table_cells(line=header_line)
    if _is_table_delimiter_line(line=header_line):
        return {"type": "table", "headers": [], "rows": []}, start + 1
    rows: list[list[str]] = []
    index = start + 1
    if index < len(lines) and _is_table_delimiter_line(line=str(lines[index] or "").strip()):
        index += 1
    while index < len(lines):
        row_line = str(lines[index] or "").strip()
        if not row_line or "|" not in row_line:
            break
        if _is_table_delimiter_line(line=row_line):
            index += 1
            continue
        row_cells = _split_table_cells(line=row_line)
        if row_cells:
            rows.append(row_cells)
        index += 1
    return {"type": "table", "headers": headers, "rows": rows}, index


def _split_table_cells(line: str) -> list[str]:
    """
    table 한 줄을 셀 목록으로 분리한다.

    Args:
        line: table 라인

    Returns:
        셀 문자열 목록
    """
    trimmed = str(line or "").strip().lstrip("|").rstrip("|")
    if not trimmed:
        return []
    return [cell.strip() for cell in trimmed.split("|")]


def _is_table_delimiter_line(line: str) -> bool:
    """
    markdown table 구분선 라인(`|---|---|`) 여부를 판별한다.

    Args:
        line: 검사 대상 라인

    Returns:
        구분선이면 True
    """
    cells = _split_table_cells(line=line)
    if not cells:
        return False
    return all(bool(re.match(r"^:?-{3,}:?$", str(cell or "").strip())) for cell in cells)
