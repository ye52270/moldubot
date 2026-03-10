from __future__ import annotations

import re

from app.models.response_contracts import LLMResponseContract
from app.services.answer_postprocessor_guard_utils import normalize_action_item_line
from app.services.answer_postprocessor_summary import extract_summary_lines, sanitize_summary_lines
from app.services.current_mail_request_intent import (
    is_current_mail_cause_analysis_request,
    is_current_mail_solution_request,
    resolve_current_mail_issue_sections,
)
from app.services.issue_analysis_renderer import render_issue_analysis_sections


def is_effectively_empty_contract(contract: LLMResponseContract) -> bool:
    """
    계약 객체가 실질적으로 비어 있는지 판별한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        의미 있는 출력 필드가 없으면 True
    """
    fields = [
        str(contract.answer or "").strip(),
        str(contract.title or "").strip(),
        str(contract.core_issue or "").strip(),
        str(contract.one_line_summary or "").strip(),
    ]
    if any(fields):
        return False
    if contract.summary_lines:
        return False
    if contract.key_points:
        return False
    if contract.action_items:
        return False
    if contract.major_points:
        return False
    if contract.required_actions:
        return False
    return len(contract.basic_info) == 0


def render_forced_section_response(user_message: str, contract: LLMResponseContract) -> str:
    """
    사용자 요청이 강제 섹션형 포맷이면 섹션 템플릿으로 렌더링한다.

    Args:
        user_message: 사용자 입력 원문
        contract: 파싱된 LLM 응답 계약

    Returns:
        강제 섹션 렌더링 문자열. 대상이 아니면 빈 문자열
    """
    if is_current_mail_cause_analysis_request(user_message=user_message):
        return _render_current_mail_cause_analysis(user_message=user_message, contract=contract)
    if is_current_mail_solution_request(user_message=user_message):
        return _render_current_mail_solution_checklist(contract=contract)
    if _is_core_action_conclusion_report_request(user_message=user_message):
        return _render_core_action_conclusion_report(contract=contract)
    if _is_schedule_owner_action_request(user_message=user_message):
        return _render_schedule_owner_action(contract=contract)
    if _is_action_items_request(user_message=user_message):
        return _render_action_items_list(contract=contract)
    return ""


def looks_like_json_contract_text(text: str) -> bool:
    """
    문자열이 JSON 계약 원문처럼 보이는지 판별한다.

    Args:
        text: 검사 대상 문자열

    Returns:
        JSON 계약 형태로 보이면 True
    """
    normalized = str(text or "").strip()
    if not normalized:
        return False
    if normalized.startswith("```"):
        fenced = re.search(r"```(?:json)?\s*([\s\S]*?)\s*```", normalized, flags=re.IGNORECASE)
        if fenced and fenced.group(1):
            normalized = str(fenced.group(1) or "").strip()
    return normalized.startswith("{") and ("format_type" in normalized or '"reply_draft"' in normalized)


def render_report_fallback_message() -> str:
    """
    보고서 요청에서 JSON 템플릿 출력 실패 시 사용자 안내 문구를 생성한다.

    Returns:
        표준 실패 안내 문자열
    """
    return "요청한 보고서 형식으로 정리할 근거를 찾지 못했습니다. 조회 조건을 조정해 다시 시도해 주세요."


def _is_core_action_conclusion_report_request(user_message: str) -> bool:
    """
    핵심/조치사항/결론 보고서 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        강제 보고서 요청이면 True
    """
    compact = str(user_message or "").replace(" ", "")
    if "보고서" not in compact:
        return False
    return ("핵심" in compact) and ("조치" in compact) and ("결론" in compact)


def _is_schedule_owner_action_request(user_message: str) -> bool:
    """
    일정/담당/조치 구분 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        강제 구분 포맷 요청이면 True
    """
    compact = str(user_message or "").replace(" ", "")
    has_target = ("일정" in compact) and ("담당" in compact) and ("조치" in compact)
    has_split = ("구분" in compact) or ("분리" in compact) or ("정리" in compact)
    return has_target and has_split


def _render_core_action_conclusion_report(contract: LLMResponseContract) -> str:
    """
    핵심/조치사항/결론 섹션 보고서를 렌더링한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        보고서 문자열
    """
    lines = _collect_contract_lines(contract=contract)
    core = str(contract.core_issue or "").strip() or (lines[0] if lines else "핵심 내용을 확인하지 못했습니다.")
    actions = sanitize_summary_lines(lines=list(contract.required_actions) + list(contract.action_items))
    if not actions:
        actions = [line for line in lines if _looks_like_action_line(line=line)]
    if not actions:
        actions = ["조치 필요 사항을 확인하지 못했습니다."]
    conclusion = str(contract.one_line_summary or "").strip()
    if not conclusion:
        conclusion = lines[-1] if lines else "추가 확인 후 결론을 보완해 주세요."
    blocks = [
        "## 핵심",
        "",
        f"- {core}",
        "",
        "## 조치사항",
        "",
    ]
    for index, action in enumerate(actions[:5], start=1):
        blocks.append(f"{index}. {action}")
    blocks.extend(["", "## 결론", "", f"- {conclusion}"])
    return "\n".join(blocks).strip()


def _render_schedule_owner_action(contract: LLMResponseContract) -> str:
    """
    일정/담당/조치 구분 섹션을 렌더링한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        구분형 문자열
    """
    lines = _collect_contract_lines(contract=contract)
    schedule_lines = [line for line in lines if _looks_like_schedule_line(line=line)]
    owner_lines = [line for line in lines if _looks_like_owner_line(line=line)]
    action_lines = [line for line in lines if _looks_like_action_line(line=line)]
    if not schedule_lines:
        schedule_lines = ["일정 정보를 확인하지 못했습니다."]
    if not owner_lines:
        owner_lines = ["담당 정보를 확인하지 못했습니다."]
    if not action_lines:
        action_lines = ["조치 정보를 확인하지 못했습니다."]
    blocks = [
        "## 일정",
        "",
        *[f"- {line}" for line in schedule_lines[:5]],
        "",
        "## 담당",
        "",
        *[f"- {line}" for line in owner_lines[:5]],
        "",
        "## 조치",
        "",
        *[f"{index}. {line}" for index, line in enumerate(action_lines[:5], start=1)],
    ]
    return "\n".join(blocks).strip()


def _render_current_mail_cause_analysis(user_message: str, contract: LLMResponseContract) -> str:
    """
    현재메일 원인 분석 요청을 원인/영향/대응 섹션으로 렌더링한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        원인 분석 섹션 문자열
    """
    sections = resolve_current_mail_issue_sections(user_message=user_message)
    if not sections:
        sections = ("cause", "impact", "response")
    return render_issue_analysis_sections(contract=contract, sections=sections)


def _render_current_mail_solution_checklist(contract: LLMResponseContract) -> str:
    """
    현재메일 해결책 요청을 가능한 원인/점검/즉시조치 체크리스트로 렌더링한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        해결 체크리스트 문자열
    """
    lines = _collect_contract_lines(contract=contract)
    cause_lines = [
        line
        for line in lines
        if _looks_like_cause_line(line=line) and not _looks_like_check_line(line=line)
    ]
    check_lines = [line for line in lines if _looks_like_check_line(line=line)]
    action_lines = [
        line
        for line in lines
        if _looks_like_action_line(line=line)
        and line not in cause_lines
        and line not in check_lines
    ]
    if not action_lines:
        action_lines = sanitize_summary_lines(lines=list(contract.required_actions) + list(contract.action_items))
    if not cause_lines:
        cause_lines = ["가능 원인을 확인하지 못했습니다."]
    if not check_lines:
        check_lines = ["점검 순서를 확인하지 못했습니다."]
    if not action_lines:
        action_lines = ["즉시 조치를 확인하지 못했습니다."]
    blocks = [
        "## 가능한 원인",
        "",
        *[f"- {line}" for line in cause_lines[:4]],
        "",
        "## 점검 순서",
        "",
        *[f"{index}. {line}" for index, line in enumerate(check_lines[:5], start=1)],
        "",
        "## 즉시 조치",
        "",
        *[f"{index}. {line}" for index, line in enumerate(action_lines[:5], start=1)],
    ]
    return "\n".join(blocks).strip()


def _collect_contract_lines(contract: LLMResponseContract) -> list[str]:
    """
    계약 객체에서 섹션 렌더링에 활용할 라인 후보를 수집한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        중복 제거된 라인 목록
    """
    candidates: list[str] = []
    candidates.extend(sanitize_summary_lines(lines=list(contract.summary_lines)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.major_points)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.key_points)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.required_actions)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.action_items)))
    candidates.extend(extract_summary_lines(answer=contract.answer))
    unique: list[str] = []
    for candidate in candidates:
        normalized = str(candidate or "").strip()
        if not normalized:
            continue
        if normalized in unique:
            continue
        unique.append(normalized)
    return unique


def _looks_like_schedule_line(line: str) -> bool:
    """
    라인이 일정 정보인지 추정한다.

    Args:
        line: 검사할 문장

    Returns:
        일정 정보로 보이면 True
    """
    text = str(line or "")
    patterns = (r"\d{4}-\d{1,2}-\d{1,2}", r"\d{1,2}:\d{2}", r"\d{1,2}월", r"\d{1,2}일")
    if any(re.search(pattern, text) for pattern in patterns):
        return True
    return any(token in text for token in ("일정", "기한", "마감", "이번주", "다음주"))


def _looks_like_owner_line(line: str) -> bool:
    """
    라인이 담당 정보인지 추정한다.

    Args:
        line: 검사할 문장

    Returns:
        담당 정보로 보이면 True
    """
    text = str(line or "")
    if any(token in text for token in ("담당", "팀", "부서", "매니저", "님")):
        return True
    return bool(re.search(r"[가-힣]{2,4}", text))


def _looks_like_action_line(line: str) -> bool:
    """
    라인이 조치/액션 정보인지 추정한다.

    Args:
        line: 검사할 문장

    Returns:
        조치 정보로 보이면 True
    """
    text = str(line or "")
    return any(token in text for token in ("조치", "확인", "요청", "회신", "검토", "업데이트", "적용"))


def _looks_like_cause_line(line: str) -> bool:
    """
    라인이 원인 정보인지 추정한다.

    Args:
        line: 검사할 문장

    Returns:
        원인 정보로 보이면 True
    """
    text = str(line or "")
    return any(token in text for token in ("원인", "이유", "문제", "이슈", "만료", "누락", "불일치"))


def _looks_like_check_line(line: str) -> bool:
    """
    라인이 점검 절차 정보인지 추정한다.

    Args:
        line: 검사할 문장

    Returns:
        점검 절차로 보이면 True
    """
    text = str(line or "")
    return any(token in text for token in ("점검", "확인", "체크", "검증", "로그", "만료일"))


def _is_action_items_request(user_message: str) -> bool:
    """
    액션 아이템 추출 요청 여부를 판별한다.

    Args:
        user_message: 사용자 입력 원문

    Returns:
        액션 아이템 요청이면 True
    """
    compact = str(user_message or "").replace(" ", "")
    lowered = compact.lower()
    return (
        ("액션아이템" in compact)
        or ("actionitem" in lowered)
        or ("할일" in compact)
        or ("조치사항" in compact)
    )


def _render_action_items_list(contract: LLMResponseContract) -> str:
    """
    액션 아이템 요청에 대해 번호 목록 형식으로 강제 렌더링한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        액션 아이템 번호 목록 문자열
    """
    candidates = sanitize_summary_lines(lines=list(contract.action_items))
    if not candidates:
        candidates = sanitize_summary_lines(lines=list(contract.required_actions))
    if not candidates:
        candidates = sanitize_summary_lines(lines=list(contract.summary_lines))
    if not candidates:
        candidates = sanitize_summary_lines(lines=list(contract.key_points))
    if not candidates:
        candidates = extract_summary_lines(answer=contract.answer)
    normalized: list[str] = []
    for candidate in candidates:
        cleaned = normalize_action_item_line(text=candidate)
        if not cleaned:
            continue
        if cleaned in normalized:
            continue
        normalized.append(cleaned)
    if not normalized:
        normalized = ["액션 아이템을 확인하지 못했습니다."]
    lines = ["## 액션 아이템", ""]
    for index, item in enumerate(normalized[:6], start=1):
        lines.append(f"{index}. {item}")
    return "\n".join(lines).strip()
