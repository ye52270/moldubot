from __future__ import annotations

import re
from typing import Any

from app.models.response_contracts import LLMResponseContract
from app.services.query_artifact_extractor import (
    extract_query_artifact_candidates,
    rank_query_artifact_candidates,
)
from app.services.answer_postprocessor_summary import sanitize_summary_lines
from app.services.current_mail_intent_policy import (
    is_current_mail_direct_fact_request,
    is_translation_like_request_text,
    render_current_mail_grounded_safe_message,
    should_apply_current_mail_grounded_safe_guard,
)
from app.services.mail_text_utils import extract_recipients_from_body
from app.services.text_overlap_utils import extract_overlap_tokens, token_overlap_score


def render_current_mail_recipients_table(
    user_message: str,
    contract: LLMResponseContract,
) -> str:
    """
    현재메일 수신자 표 요청을 markdown 표 포맷으로 강제 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        contract: 파싱된 JSON 계약

    Returns:
        렌더링 문자열. 적용 대상이 아니면 빈 문자열
    """
    if not is_current_mail_recipients_table_request(user_message=user_message):
        return ""
    recipient_text = resolve_recipient_text(contract=contract)
    recipients = split_recipients(recipient_text=recipient_text)
    if not recipients:
        return "## 주요 수신자 정보\n\n수신자 정보가 확인되지 않았습니다."
    rows = ["## 주요 수신자 정보", "", "| 번호 | 수신자 |", "|---|---|"]
    for index, recipient in enumerate(recipients[:10], start=1):
        rows.append(f"| {index} | {recipient} |")
    return "\n".join(rows).strip()


def render_current_mail_recipients_from_tool_payload(
    user_message: str,
    tool_payload: dict[str, Any],
) -> str:
    """
    현재메일 수신자 질의를 tool payload 기반으로 강제 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        tool_payload: 직전 tool payload

    Returns:
        렌더링 문자열. 적용 대상이 아니거나 데이터가 없으면 빈 문자열
    """
    if not is_current_mail_recipients_request(user_message=user_message):
        return ""
    mail_context = tool_payload.get("mail_context")
    if not isinstance(mail_context, dict):
        return ""
    body_excerpt = str(mail_context.get("body_excerpt") or "").strip()
    recipients = extract_recipients_from_body(text=body_excerpt)
    if not recipients:
        fallback_candidates = (
            str(mail_context.get("to_recipients") or "").strip(),
            str(mail_context.get("recipients") or "").strip(),
            str(mail_context.get("to") or "").strip(),
            str(mail_context.get("receiver") or "").strip(),
        )
        for candidate in fallback_candidates:
            if not candidate:
                continue
            recipients = split_recipients(recipient_text=candidate)
            if recipients:
                break
    if not recipients:
        return "현재메일 수신자 정보를 확인하지 못했습니다."
    unique_recipients = split_recipients(recipient_text=", ".join(recipients))
    if not unique_recipients:
        return "현재메일 수신자 정보를 확인하지 못했습니다."
    if is_current_mail_recipients_table_request(user_message=user_message):
        rows = ["## 주요 수신자 정보", "", "| 번호 | 수신자 |", "|---|---|"]
        for index, recipient in enumerate(unique_recipients[:10], start=1):
            rows.append(f"| {index} | {recipient} |")
        return "\n".join(rows).strip()
    lines = ["현재메일 수신자:", ""]
    for index, recipient in enumerate(unique_recipients[:10], start=1):
        lines.append(f"{index}. {recipient}")
    return "\n".join(lines).strip()


def render_current_mail_issue_action_split(
    user_message: str,
    contract: LLMResponseContract,
) -> str:
    """
    현재메일 핵심문제/해야할일 분리 요청을 섹션 포맷으로 강제 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        contract: 파싱된 JSON 계약

    Returns:
        렌더링 문자열. 적용 대상이 아니면 빈 문자열
    """
    if not is_current_mail_issue_action_request(user_message=user_message):
        return ""
    core_issue = str(contract.core_issue or "").strip()
    if not core_issue:
        summary_lines = sanitize_summary_lines(lines=list(contract.summary_lines))
        core_issue = summary_lines[0] if summary_lines else ""
    action_candidates = sanitize_summary_lines(lines=list(contract.required_actions))
    if not action_candidates:
        action_candidates = sanitize_summary_lines(lines=list(contract.action_items))
    if not action_candidates:
        action_candidates = sanitize_summary_lines(lines=list(contract.key_points))
    blocks = ["## 핵심 문제", ""]
    blocks.append(f"- {core_issue}" if core_issue else "- 핵심 문제 정보를 확인하지 못했습니다.")
    blocks.extend(["", "## 해야 할 일", ""])
    if action_candidates:
        for index, item in enumerate(action_candidates[:5], start=1):
            blocks.append(f"{index}. {item}")
    else:
        blocks.append("1. 해야 할 일 정보를 확인하지 못했습니다.")
    return "\n".join(blocks).strip()


def render_current_mail_direct_value_from_tool_payload(
    user_message: str,
    tool_payload: dict[str, Any],
) -> str:
    """
    현재메일 direct-value 질의를 본문 근거에서 값 중심으로 강제 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        tool_payload: 직전 tool payload

    Returns:
        값 추출 응답 문자열. 적용 대상이 아니면 빈 문자열
    """
    if is_translation_like_request_text(user_message=user_message):
        return ""
    action = str(tool_payload.get("action") or "").strip().lower()
    if action != "current_mail":
        return ""
    if not _resolve_direct_fact_render_decision(
        user_message=user_message,
        tool_payload=tool_payload,
    ):
        return ""
    mail_context = tool_payload.get("mail_context")
    if not isinstance(mail_context, dict):
        return "현재메일 본문에서 요청한 직접값을 확인하지 못했습니다."
    candidates = extract_query_artifact_candidates(mail_context=mail_context)
    ranked = rank_query_artifact_candidates(user_message=user_message, candidates=candidates)
    if not ranked:
        return "현재메일 본문에서 요청한 직접값을 확인하지 못했습니다."
    lines = ["현재메일 본문에서 확인된 값:", ""]
    for index, candidate in enumerate(ranked[:3], start=1):
        lines.append(f"{index}. `{candidate}`")
    lines.extend(["", "근거: 현재메일 본문 발췌 기준"])
    return "\n".join(lines).strip()


def _resolve_direct_fact_render_decision(
    user_message: str,
    tool_payload: dict[str, Any],
) -> bool:
    """
    direct-value 강제 렌더링 허용 여부를 정책 메타 우선으로 결정한다.

    Args:
        user_message: 사용자 입력 원문
        tool_payload: 직전 tool payload

    Returns:
        direct-value 렌더링 허용 여부
    """
    postprocess_policy = tool_payload.get("postprocess_policy")
    if isinstance(postprocess_policy, dict):
        decision = postprocess_policy.get("direct_fact_decision")
        if isinstance(decision, bool):
            return decision
    return is_current_mail_direct_fact_request(
        user_message=user_message,
        has_current_mail_context=True,
    )


def render_current_mail_manager_single_paragraph(
    user_message: str,
    contract: LLMResponseContract,
) -> str:
    """
    현재메일 팀장 보고용 한 단락 요청을 단일 문단으로 강제 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        contract: 파싱된 JSON 계약

    Returns:
        단일 문단 텍스트. 적용 대상이 아니면 빈 문자열
    """
    if not is_current_mail_manager_single_paragraph_request(user_message=user_message):
        return ""
    fragments: list[str] = []
    title = str(contract.title or "").strip()
    if title:
        fragments.append(f"제목은 '{title}'입니다")
    core_issue = str(contract.core_issue or "").strip()
    if core_issue:
        fragments.append(f"핵심 이슈는 {core_issue}")
    major_points = sanitize_summary_lines(lines=list(contract.major_points))
    if major_points:
        fragments.append(f"주요 내용은 {', '.join(major_points[:2])}입니다")
    required_actions = sanitize_summary_lines(lines=list(contract.required_actions))
    if required_actions:
        fragments.append(f"필요 조치는 {', '.join(required_actions[:2])}입니다")
    one_line = str(contract.one_line_summary or "").strip()
    if one_line:
        fragments.append(f"종합하면 {one_line}")
    if not fragments:
        fallback_lines = sanitize_summary_lines(lines=list(contract.summary_lines))
        if fallback_lines:
            fragments.append(" ".join(fallback_lines[:2]))
        else:
            return ""
    paragraph = ". ".join(part.rstrip(".") for part in fragments if part).strip()
    if not paragraph.endswith("."):
        paragraph += "."
    return paragraph


def is_current_mail_recipients_table_request(user_message: str) -> bool:
    """
    현재메일 수신자 표 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        현재메일 + 수신자 + 표 요청이면 True
    """
    text = str(user_message or "").replace(" ", "")
    return ("현재메일" in text) and ("수신자" in text) and ("표" in text)


def is_current_mail_recipients_request(user_message: str) -> bool:
    """
    현재메일 수신자 질의 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        현재메일 수신자 질의면 True
    """
    compact = str(user_message or "").replace(" ", "").lower()
    if "현재메일" not in compact:
        return False
    if "역할" in compact:
        return False
    if any(token in compact for token in ("todo", "할일", "액션", "마감", "기한", "due")):
        return False
    recipient_tokens = ("수신자", "받는사람", "recipient", "to")
    return any(token in compact for token in recipient_tokens)


def resolve_recipient_text(contract: LLMResponseContract) -> str:
    """
    계약 객체에서 수신자 문자열을 추출한다.

    Args:
        contract: 파싱된 JSON 계약

    Returns:
        수신자 원문 문자열
    """
    basic_info = contract.basic_info if isinstance(contract.basic_info, dict) else {}
    key_candidates = ("수신자", "받는 사람", "to", "recipient")
    lowered = {str(key).strip().lower(): str(value).strip() for key, value in basic_info.items()}
    for key in key_candidates:
        value = lowered.get(key.lower(), "")
        if value:
            return value
    answer_text = str(contract.answer or "")
    matched = re.search(r"(?:수신자|받는\s*사람|to)\s*[:：]\s*([^\n]+)", answer_text, flags=re.IGNORECASE)
    if matched:
        return str(matched.group(1) or "").strip()
    return ""


def split_recipients(recipient_text: str) -> list[str]:
    """
    수신자 원문 문자열을 개별 수신자 목록으로 분리한다.

    Args:
        recipient_text: 수신자 원문

    Returns:
        정규화된 수신자 목록
    """
    normalized = str(recipient_text or "").strip()
    if not normalized:
        return []
    parts = re.split(r"[,;/\n]| 및 ", normalized)
    recipients: list[str] = []
    for part in parts:
        text = str(part or "").strip()
        if text and text not in recipients:
            recipients.append(text)
    return recipients


def is_current_mail_issue_action_request(user_message: str) -> bool:
    """
    현재메일 핵심문제/해야할일 분리 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        분리 포맷 요청이면 True
    """
    text = str(user_message or "").replace(" ", "")
    if "현재메일" not in text:
        return False
    has_issue = ("핵심문제" in text) or ("핵심이슈" in text)
    has_action = ("해야할일" in text) or ("조치" in text) or ("액션" in text)
    has_split = ("분리" in text) or ("구분" in text)
    return has_issue and has_action and has_split


def is_current_mail_manager_single_paragraph_request(user_message: str) -> bool:
    """
    현재메일 팀장 보고용 한 단락 요약 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        단락 요약 강제 대상이면 True
    """
    text = str(user_message or "").replace(" ", "")
    if "현재메일" not in text:
        return False
    has_manager_tone = ("팀장" in text) or ("보고용" in text)
    has_single_paragraph = ("한단락" in text) or ("한문단" in text)
    has_summary = "요약" in text
    return has_manager_tone and has_single_paragraph and has_summary


def render_current_mail_grounded_safe_response(
    user_message: str,
    answer: str,
    tool_payload: dict[str, Any],
) -> str:
    """
    현재메일 근거가 얕을 때 과도한 추론 답변을 안전 템플릿으로 축약한다.

    Args:
        user_message: 사용자 입력 원문
        answer: 모델 생성 답변
        tool_payload: 직전 tool payload

    Returns:
        안전 템플릿 응답. 적용 대상이 아니면 빈 문자열
    """
    if str(tool_payload.get("action") or "").strip().lower() != "current_mail":
        return ""
    if not should_apply_current_mail_grounded_safe_guard(user_message=user_message):
        return ""
    mail_context = tool_payload.get("mail_context")
    if not isinstance(mail_context, dict):
        return ""
    summary_text = str(mail_context.get("summary_text") or "").strip()
    body_excerpt = str(mail_context.get("body_excerpt") or "").strip()
    if not summary_text:
        return ""
    if _already_uncertainty_answer(answer=answer):
        return ""
    if not _should_force_grounded_safe_response(
        user_message=user_message,
        answer=answer,
        summary_text=summary_text,
        body_excerpt=body_excerpt,
    ):
        return ""
    return render_current_mail_grounded_safe_message(
        user_message=user_message,
        summary_text=summary_text,
    )


def _should_force_grounded_safe_response(
    user_message: str,
    answer: str,
    summary_text: str,
    body_excerpt: str,
) -> bool:
    """
    근거 대비 답변 과생성 여부를 판별해 안전 템플릿 강제 적용 여부를 계산한다.

    Args:
        user_message: 사용자 입력 원문
        answer: 모델 생성 답변
        summary_text: 현재메일 요약
        body_excerpt: 현재메일 본문 발췌

    Returns:
        안전 템플릿 강제 대상이면 True
    """
    source_text = f"{summary_text}\n{body_excerpt}".strip()
    source_tokens = set(extract_overlap_tokens(text=source_text))
    answer_tokens = set(extract_overlap_tokens(text=answer))
    if len(answer_tokens) < 3:
        return False
    overlap = token_overlap_score(point_tokens=source_tokens, candidate=answer)
    has_named_entity_pattern = bool(re.search(r"[가-힣]{2,}\s?(수석|차장|매니저|팀장|파트장)", answer))
    has_large_number = bool(re.search(r"\d{2,}", answer))
    if overlap <= 0.35 and (has_named_entity_pattern or has_large_number):
        return True
    if overlap <= 0.28 and len(answer_tokens) <= 6:
        return True
    if len(source_tokens) <= 8 and overlap <= 0.30:
        return True
    return False


def _already_uncertainty_answer(answer: str) -> bool:
    """
    기존 답변이 이미 근거 한계를 명시하는지 확인한다.

    Args:
        answer: 모델 생성 답변

    Returns:
        한계 명시 응답이면 True
    """
    compact = str(answer or "").replace(" ", "")
    uncertainty_tokens = ("확인할수없", "모르겠", "정보가없", "근거가없", "언급되어있지않")
    return any(token in compact for token in uncertainty_tokens)
