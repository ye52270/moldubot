from __future__ import annotations

from app.models.response_contracts import LLMResponseContract
from app.services.answer_postprocessor_code_snippet import render_auto_code_snippet_text
from app.services.answer_postprocessor_rendering_summary import render_summary_contract
from app.services.answer_postprocessor_summary import (
    is_report_request,
    is_summary_request,
    normalize_multiline_text,
)

SHORT_ANSWER_MAX_CHARS = 120
MIN_STRUCTURED_LINE_COUNT = 2
STRUCTURED_LINE_MAX_PICK = 6
STRUCTURED_ADVANTAGE_MULTIPLIER = 2


def render_contract_answer(user_message: str, contract: LLMResponseContract) -> str:
    """
    JSON 계약 응답을 사용자 출력 포맷으로 렌더링한다.

    Args:
        user_message: 사용자 입력
        contract: 파싱된 JSON 계약

    Returns:
        최종 렌더링 문자열
    """
    if is_summary_request(user_message=user_message):
        return render_summary_contract(user_message=user_message, contract=contract)
    if is_report_request(user_message=user_message):
        return render_report_contract(contract=contract)
    return render_general_contract(user_message=user_message, contract=contract)


def render_report_contract(contract: LLMResponseContract) -> str:
    """
    report JSON 계약을 보고서 텍스트로 렌더링한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        보고서 출력 문자열
    """
    blocks: list[str] = []
    title = contract.title or "보고서"
    blocks.append(title)
    if contract.summary_lines:
        blocks.append("\n".join(f"- {item}" for item in contract.summary_lines))
    if contract.key_points:
        blocks.append("핵심 포인트:\n" + "\n".join(f"- {item}" for item in contract.key_points))
    if contract.action_items:
        blocks.append("후속 액션:\n" + "\n".join(f"- {item}" for item in contract.action_items))
    if not contract.summary_lines and not contract.key_points and not contract.action_items:
        blocks.append(contract.answer)
    return normalize_multiline_text(text="\n\n".join(blocks))


def render_general_contract(user_message: str, contract: LLMResponseContract) -> str:
    """
    general JSON 계약을 일반 답변 텍스트로 렌더링한다.

    Args:
        user_message: 사용자 입력
        contract: JSON 계약 객체

    Returns:
        일반 답변 문자열
    """
    if contract.reply_draft:
        return _normalize_reply_draft_text(text=contract.reply_draft)
    if _should_prefer_structured_lines(contract=contract):
        return _render_general_structured_lines(contract=contract)
    if contract.answer:
        code_snippet = render_auto_code_snippet_text(
            user_message=user_message,
            answer=contract.answer,
        )
        if code_snippet:
            return code_snippet
        return normalize_multiline_text(text=contract.answer)
    if str(contract.format_type or "").strip().lower() == "summary":
        summary_only = _dedupe_lines([str(item or "").strip() for item in contract.summary_lines])
        if summary_only:
            return normalize_multiline_text(text="\n".join(f"- {item}" for item in summary_only))
    if _has_general_multi_source_content(contract=contract):
        return _render_general_merged_lines(contract=contract)
    if contract.summary_lines:
        return normalize_multiline_text(text="\n".join(contract.summary_lines))
    if contract.action_items:
        return normalize_multiline_text(text="\n".join(f"- {item}" for item in contract.action_items))
    if contract.required_actions:
        return normalize_multiline_text(text="\n".join(f"- {item}" for item in contract.required_actions))
    if contract.major_points:
        return normalize_multiline_text(text="\n".join(f"- {item}" for item in contract.major_points))
    if contract.key_points:
        return normalize_multiline_text(text="\n".join(f"- {item}" for item in contract.key_points))
    return ""


def _has_general_multi_source_content(contract: LLMResponseContract) -> bool:
    """
    general 계약에서 다중 필드 병합 렌더가 필요한지 판단한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        2개 이상 콘텐츠 필드가 채워져 있으면 True
    """
    filled_count = 0
    for rows in (
        list(contract.summary_lines),
        list(contract.major_points),
        list(contract.key_points),
        list(contract.action_items),
        list(contract.required_actions),
    ):
        if any(str(item or "").strip() for item in rows):
            filled_count += 1
    return filled_count >= 2


def _render_general_merged_lines(contract: LLMResponseContract) -> str:
    """
    general 계약의 다중 필드를 중복 없이 병합해 불릿 목록으로 렌더링한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        병합된 불릿 문자열
    """
    candidates = [
        *[str(item or "").strip() for item in contract.summary_lines],
        *[str(item or "").strip() for item in contract.major_points],
        *[str(item or "").strip() for item in contract.key_points],
        *[str(item or "").strip() for item in contract.action_items],
        *[str(item or "").strip() for item in contract.required_actions],
    ]
    deduped = _dedupe_lines(candidates)
    return normalize_multiline_text(text="\n".join(f"- {item}" for item in deduped))


def _dedupe_lines(candidates: list[str]) -> list[str]:
    """
    라인 목록을 대소문자 무시 기준으로 중복 제거한다.

    Args:
        candidates: 원본 라인 목록

    Returns:
        순서를 보존한 중복 제거 라인 목록
    """
    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in candidates:
        text = str(candidate or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped


def _normalize_reply_draft_text(text: str) -> str:
    """
    회신 본문 텍스트를 단락 구분(빈 줄) 유지 형태로 정규화한다.

    Args:
        text: 회신 본문 원문

    Returns:
        단락 구분이 유지된 정규화 텍스트
    """
    normalized = str(text or "")
    normalized = (
        normalized.replace("\\r\\n", "\n")
        .replace("\\n", "\n")
        .replace("\\r", "\n")
        .replace("\r\n", "\n")
        .replace("\r", "\n")
        .strip()
    )
    lines = [line.strip() for line in normalized.split("\n")]
    joined = "\n".join(lines)
    return joined.replace("\n\n\n", "\n\n").strip()


def _render_general_structured_lines(contract: LLMResponseContract) -> str:
    """
    general 계약의 구조 라인 필드를 불릿 목록으로 렌더링한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        구조 라인 불릿 문자열. 후보가 없으면 빈 문자열
    """
    deduped = _collect_general_structured_lines(contract=contract)
    if not deduped:
        return ""
    return normalize_multiline_text(text="\n".join(f"- {item}" for item in deduped))


def _should_prefer_structured_lines(contract: LLMResponseContract) -> bool:
    """
    general 계약에서 단문 answer 대신 구조 라인 렌더를 우선할지 판단한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        구조 라인 우선 렌더 대상이면 True
    """
    answer_text = str(contract.answer or "").strip()
    if not answer_text:
        return False
    if len(answer_text) > SHORT_ANSWER_MAX_CHARS:
        return False
    structured_lines = _collect_general_structured_lines(contract=contract)
    if len(structured_lines) < MIN_STRUCTURED_LINE_COUNT:
        return False
    structured_chars = sum(len(line) for line in structured_lines[:STRUCTURED_LINE_MAX_PICK])
    return structured_chars >= (len(answer_text) * STRUCTURED_ADVANTAGE_MULTIPLIER)


def _collect_general_structured_lines(contract: LLMResponseContract) -> list[str]:
    """
    general 계약에서 정보성 구조 라인 후보를 수집한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        중복 제거된 구조 라인 목록
    """
    candidates = [
        *[str(item or "").strip() for item in contract.summary_lines],
        *[str(item or "").strip() for item in contract.major_points],
        *[str(item or "").strip() for item in contract.key_points],
    ]
    return _dedupe_lines(candidates)
