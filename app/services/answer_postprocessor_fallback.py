from __future__ import annotations

import json
from typing import Any

from app.core.intent_rules import is_code_review_query, is_mail_summary_skill_query
from app.services.answer_postprocessor_code_snippet import render_auto_code_snippet_text
from app.models.response_contracts import LLMResponseContract, SummaryResponseContract
from app.services.answer_postprocessor_contract_utils import augment_contract_with_tool_payload
from app.services.answer_postprocessor_guards import (
    looks_like_json_contract_text,
    render_report_fallback_message,
)
from app.services.answer_postprocessor_rendering import render_contract_answer
from app.services.answer_postprocessor_reply_draft import (
    recover_reply_draft_from_json_text,
    recover_reply_draft_from_plain_text,
)
from app.services.answer_postprocessor_summary import (
    extract_summary_lines,
    is_current_mail_summary_request,
    is_report_request,
    is_summary_request,
    render_summary_lines_for_request,
    resolve_summary_line_target,
)
from app.services.answer_table_spec import render_current_mail_people_roles_table


def render_fallback_answer(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
) -> tuple[str, str]:
    """
    계약 렌더 실패 시 유형별 fallback 응답을 렌더링한다.

    Args:
        user_message: 정규화 사용자 입력
        answer: 정규화 모델 응답
        tool_payload: 툴 payload

    Returns:
        (route, rendered_answer)
    """
    forced_people_roles_table = render_current_mail_people_roles_table(
        user_message=user_message,
        mail_context=tool_payload.get("mail_context"),
    )
    if forced_people_roles_table:
        return "current_mail_people_roles_table", forced_people_roles_table

    reply_draft_fallback = recover_reply_draft_from_json_text(
        user_message=user_message,
        answer=answer,
    )
    if reply_draft_fallback:
        return "reply_draft_json_text", reply_draft_fallback

    reply_draft_plain_fallback = recover_reply_draft_from_plain_text(
        user_message=user_message,
        answer=answer,
    )
    if reply_draft_plain_fallback:
        return "reply_draft_plain_text", reply_draft_plain_fallback

    malformed_current_mail_fallback = _recover_current_mail_summary_from_tool_payload(
        user_message=user_message,
        answer=answer,
        tool_payload=tool_payload,
    )
    if malformed_current_mail_fallback:
        return "current_mail_summary_recovery", malformed_current_mail_fallback

    if is_code_review_query(user_message=user_message) and not looks_like_json_contract_text(text=answer):
        return "code_review_text", answer

    if is_report_request(user_message=user_message):
        if looks_like_json_contract_text(text=answer):
            return "report_template_guard", render_report_fallback_message()
        return "report_text", answer

    generic_json_object_rendered = _render_generic_json_object_text(
        user_message=user_message,
        answer=answer,
    )
    if generic_json_object_rendered:
        return "generic_json_object_text", generic_json_object_rendered

    if is_summary_request(user_message=user_message):
        if (
            is_current_mail_summary_request(user_message=user_message)
            and not is_mail_summary_skill_query(user_message=user_message)
            and '"format_type"' not in answer
        ):
            return "summary_freeform_text", answer
        if '"format_type"' in answer:
            if is_current_mail_summary_request(user_message=user_message):
                return "summary_json_template_guard_current_mail", "현재메일 요약 형식 변환에 실패했습니다. 다시 시도해 주세요."
            return "summary_json_template_guard", "응답 형식 변환에 실패했습니다. 다시 시도해 주세요."
        line_target = resolve_summary_line_target(user_message=user_message)
        summary_lines = extract_summary_lines(answer=answer)
        contract = SummaryResponseContract(
            requested_line_target=line_target,
            summary_lines=summary_lines,
        )
        return "summary_text", render_summary_lines_for_request(
            user_message=user_message,
            lines=contract.summary_lines,
        )

    if looks_like_json_contract_text(text=answer):
        return "json_template_guard", "응답 형식 변환에 실패했습니다. 다시 시도해 주세요."

    auto_code_snippet = render_auto_code_snippet_text(
        user_message=user_message,
        answer=answer,
    )
    if auto_code_snippet:
        return "auto_code_snippet_text", auto_code_snippet

    return "general_text", answer


def _recover_current_mail_summary_from_tool_payload(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
) -> str:
    """
    현재메일 요약에서 malformed JSON 조각이 노출될 때 tool payload로 표준 요약을 복구한다.

    Args:
        user_message: 사용자 입력 원문
        answer: 모델 응답 텍스트
        tool_payload: 직전 tool payload

    Returns:
        복구 렌더 문자열. 조건 불충족 시 빈 문자열
    """
    if not is_current_mail_summary_request(user_message=user_message):
        return ""
    if is_mail_summary_skill_query(user_message=user_message):
        return ""
    if '"format_type"' not in str(answer or ""):
        return ""
    contract = LLMResponseContract(format_type="summary")
    if isinstance(tool_payload.get("mail_context"), dict):
        contract = augment_contract_with_tool_payload(
            user_message=user_message,
            contract=contract,
            tool_payload=tool_payload,
        )
    rendered = render_contract_answer(user_message=user_message, contract=contract)
    return str(rendered or "").strip()


def _render_generic_json_object_text(user_message: str, answer: str) -> str:
    """
    `format_type` 계약이 아닌 일반 JSON 객체 응답을 읽기 쉬운 텍스트로 변환한다.

    Args:
        user_message: 사용자 입력
        answer: 모델 응답 텍스트

    Returns:
        변환된 텍스트. 변환 대상이 아니면 빈 문자열
    """
    normalized = str(answer or "").strip()
    if not normalized:
        return ""
    if not _is_structuring_request(user_message=user_message):
        return ""
    if looks_like_json_contract_text(text=normalized):
        return ""
    payload = _parse_json_object_text(text=normalized)
    if not isinstance(payload, dict) or not payload:
        return ""
    rendered_lines = _render_json_object_lines(payload=payload)
    if not rendered_lines:
        return ""
    return "\n".join(rendered_lines).strip()


def _is_structuring_request(user_message: str) -> bool:
    """
    일반 JSON 객체를 문장형으로 렌더링할 구조화 요청인지 판별한다.

    Args:
        user_message: 사용자 입력

    Returns:
        요약/정리 계열 요청이면 True
    """
    compact = str(user_message or "").replace(" ", "")
    if not compact:
        return False
    return ("요약" in compact) or ("정리" in compact)


def _parse_json_object_text(text: str) -> dict[str, Any] | None:
    """
    문자열에서 JSON 객체를 파싱한다.

    Args:
        text: JSON 후보 문자열

    Returns:
        파싱된 dict 객체. 실패 시 None
    """
    candidate = str(text or "").strip()
    if candidate.startswith("```"):
        fenced = candidate.replace("```json", "").replace("```JSON", "").replace("```", "").strip()
        candidate = fenced
    if not candidate.startswith("{"):
        return None
    try:
        parsed = json.loads(candidate)
    except json.JSONDecodeError:
        return None
    if isinstance(parsed, dict):
        return parsed
    return None


def _render_json_object_lines(payload: dict[str, Any]) -> list[str]:
    """
    JSON 객체를 사람이 읽기 좋은 불릿 라인으로 변환한다.

    Args:
        payload: 파싱된 JSON 객체

    Returns:
        렌더링 라인 목록
    """
    lines: list[str] = []
    for key, value in payload.items():
        key_text = str(key or "").strip()
        if not key_text:
            continue
        value_lines = _render_json_value_lines(value=value, depth=0)
        if not value_lines:
            continue
        if len(value_lines) == 1 and not value_lines[0].startswith("- "):
            lines.append(f"{key_text}: {value_lines[0]}")
            continue
        lines.append(f"{key_text}:")
        lines.extend(value_lines)
    return lines


def _render_json_value_lines(value: Any, depth: int) -> list[str]:
    """
    JSON value를 깊이 기반 라인으로 렌더링한다.

    Args:
        value: JSON value
        depth: 중첩 깊이

    Returns:
        렌더링 라인 목록
    """
    indent = "  " * max(depth, 0)
    if isinstance(value, str):
        text = str(value or "").strip()
        return [text] if text else []
    if isinstance(value, (int, float, bool)):
        return [str(value)]
    if value is None:
        return []
    if isinstance(value, list):
        lines: list[str] = []
        for item in value[:8]:
            item_lines = _render_json_value_lines(value=item, depth=depth + 1)
            if not item_lines:
                continue
            head = str(item_lines[0]).lstrip()
            if head.startswith("- "):
                lines.append(f"{indent}- {head[2:]}")
            else:
                lines.append(f"{indent}- {head}")
            for tail in item_lines[1:]:
                lines.append(f"{indent}  {str(tail).lstrip()}")
        return lines
    if isinstance(value, dict):
        lines: list[str] = []
        for key, nested_value in list(value.items())[:8]:
            key_text = str(key or "").strip()
            if not key_text:
                continue
            nested_lines = _render_json_value_lines(value=nested_value, depth=depth + 1)
            if not nested_lines:
                continue
            if len(nested_lines) == 1 and not nested_lines[0].startswith("- "):
                lines.append(f"{indent}- {key_text}: {nested_lines[0]}")
                continue
            lines.append(f"{indent}- {key_text}:")
            for nested in nested_lines:
                lines.append(f"{indent}  {nested}")
        return lines
    return [str(value)]
