from __future__ import annotations

import re

from app.core.logging_config import get_logger
from app.core.intent_rules import is_mail_summary_skill_query
from app.models.response_contracts import LLMResponseContract, SummaryResponseContract
from app.services.answer_postprocessor_rendering_standard import (
    resolve_basic_info_value,
    resolve_core_issue_text,
    resolve_major_points,
    resolve_one_line_summary,
    resolve_required_actions,
    resolve_subject_text,
)
from app.services.answer_postprocessor_rendering_utils import (
    collect_standard_summary_missing_fields,
    render_major_points,
    render_required_actions,
)
from app.services.answer_postprocessor_summary import (
    extract_summary_lines,
    is_current_mail_summary_request,
    is_explicit_line_summary_request,
    is_summary_request,
    render_summary_lines_for_request,
    sanitize_summary_lines,
    split_headline_and_detail,
    resolve_summary_line_target,
)

logger = get_logger("app.services.answer_postprocessor_rendering")


def render_summary_contract(user_message: str, contract: LLMResponseContract) -> str:
    """
    summary/detailed_summary JSON 계약을 사용자 요청 포맷으로 렌더링한다.

    Args:
        user_message: 사용자 입력
        contract: JSON 계약 객체

    Returns:
        요약 결과 문자열
    """
    if should_render_standard_summary(user_message=user_message, contract=contract):
        return render_standard_summary_contract(contract=contract)

    line_target = resolve_summary_line_target(user_message=user_message)
    if is_explicit_line_summary_request(user_message=user_message):
        summary_lines = _build_explicit_line_summary(contract=contract, line_target=line_target)
    else:
        summary_lines = _build_summary_lines_for_target(contract=contract, line_target=line_target)
    normalized = SummaryResponseContract(
        requested_line_target=line_target,
        summary_lines=summary_lines,
    )
    rendered = render_summary_lines_for_request(
        user_message=user_message,
        lines=normalized.summary_lines,
    )
    if contract.key_points and not is_explicit_line_summary_request(user_message=user_message):
        key_points = [f"- {item}" for item in contract.key_points]
        rendered = f"{rendered}\n\n핵심 내용:\n" + "\n".join(key_points)
    return rendered


def should_render_standard_summary(user_message: str, contract: LLMResponseContract) -> bool:
    """
    표준 섹션형 요약 템플릿 렌더링 대상 여부를 판별한다.

    Args:
        user_message: 사용자 입력
        contract: JSON 계약 객체

    Returns:
        표준 요약 템플릿 사용 시 True
    """
    text = str(user_message or "")
    is_mail_summary_skill = is_mail_summary_skill_query(user_message=text)
    is_current_mail_summary = is_current_mail_summary_request(user_message=text)
    if not is_mail_summary_skill:
        return False
    if is_current_mail_summary and is_explicit_line_summary_request(user_message=text):
        return False
    if contract.format_type in ("standard_summary", "detailed_summary"):
        return is_current_mail_summary
    if not is_current_mail_summary:
        return False
    if "조회" in text or "검색" in text:
        return False
    if contract.format_type != "summary":
        return False
    if not is_summary_request(user_message=text):
        return False
    return not is_explicit_line_summary_request(user_message=text)


def render_standard_summary_contract(contract: LLMResponseContract) -> str:
    """
    표준 이메일 요약 섹션 템플릿으로 응답을 렌더링한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        섹션형 요약 문자열
    """
    subject = resolve_subject_text(contract=contract)
    sender = resolve_basic_info_value(contract=contract, keys=("최종 발신자", "발신자", "보낸 사람", "from"))
    recipient = resolve_basic_info_value(contract=contract, keys=("수신자", "받는 사람", "to"))
    date_text = resolve_basic_info_value(contract=contract, keys=("날짜", "전송일", "sent"))
    original_sender = resolve_basic_info_value(contract=contract, keys=("원본 문의 발신", "원문 발신", "최초 발신"))
    route_flow = resolve_basic_info_value(
        contract=contract,
        keys=("커뮤니케이션 흐름", "메일 흐름", "커뮤니케이션흐름"),
        default="",
    )
    core_issue = resolve_core_issue_text(contract=contract)
    major_points = resolve_major_points(contract=contract)
    required_actions = resolve_required_actions(contract=contract)
    recipient_roles = _render_recipient_roles(contract=contract)
    one_line_summary = resolve_one_line_summary(contract=contract, major_points=major_points)
    missing_fields = collect_standard_summary_missing_fields(
        subject=subject,
        sender=sender,
        recipient=recipient,
        date_text=date_text,
        core_issue=core_issue,
        major_points=major_points,
        required_actions=required_actions,
        one_line_summary=one_line_summary,
    )
    logger.info(
        "answer_postprocess.standard_summary_quality: missing_fields=%s major_points=%s required_actions=%s",
        ",".join(missing_fields) if missing_fields else "none",
        len(major_points),
        len(required_actions),
    )

    basic_info_rows = _build_basic_info_rows(
        sender=sender,
        recipient=recipient,
        date_text=date_text,
        original_sender=original_sender,
        route_flow=route_flow,
    )
    blocks = [
        "### 🧾 제목",
        "",
        f"{subject}",
        "",
        "---",
        "",
        "### 📋 기본 정보",
        "",
    ]
    if basic_info_rows:
        blocks.extend([
            "| 항목 | 내용 |",
            "|------|------|",
            *basic_info_rows,
            "",
            "---",
            "",
        ])
    else:
        blocks.extend(["- 확인 가능한 기본 정보가 없습니다.", "", "---", ""])
    if recipient_roles:
        blocks.extend(["### 👥 수신자 역할", "", *recipient_roles, "", "---", ""])
    if core_issue:
        blocks.extend(["### 🔎 핵심 문제 요약", "", f"{core_issue}", "", "---", ""])
    if major_points:
        blocks.extend(["### 📌 주요 내용", "", *render_major_points(major_points=major_points), "", "---", ""])
    if required_actions:
        blocks.extend(["### ✅ 조치 필요 사항", "", *render_required_actions(required_actions=required_actions), "", "---", ""])
    return "\n".join(blocks).strip()


def _render_recipient_roles(contract: LLMResponseContract) -> list[str]:
    """
    recipient_roles 계약 필드를 섹션형 markdown 목록으로 렌더링한다.

    Args:
        contract: JSON 계약 객체

    Returns:
        렌더링 라인 목록
    """
    rows = list(contract.recipient_roles or [])
    rendered: list[str] = []
    for index, row in enumerate(rows, start=1):
        recipient = str(getattr(row, "recipient", "") or "").strip()
        role = str(getattr(row, "role", "") or "").strip()
        evidence = str(getattr(row, "evidence", "") or "").strip()
        if not recipient and not role:
            continue
        headline = recipient if recipient else f"수신자 {index}"
        detail = role if role else "-"
        rendered.append(f"{index}. {headline} — {detail}")
        if evidence:
            rendered.append(f"- 근거: {evidence}")
    return rendered


def _build_basic_info_rows(
    sender: str,
    recipient: str,
    date_text: str,
    original_sender: str,
    route_flow: str,
) -> list[str]:
    """
    기본 정보 섹션의 markdown 테이블 행을 생성한다.

    Args:
        sender: 최종 발신자
        recipient: 수신자
        date_text: 날짜
        original_sender: 원본 문의 발신
        route_flow: 커뮤니케이션 단계 흐름

    Returns:
        값이 있는 항목만 포함한 markdown 행 목록
    """
    candidates = [
        ("날짜", date_text),
        ("최종 발신자", _normalize_people_display(value=sender)),
        ("수신자", _normalize_people_display(value=recipient)),
        ("원본 문의 발신", _normalize_people_display(value=original_sender)),
        ("커뮤니케이션 흐름", _normalize_route_flow_display(value=route_flow)),
    ]
    rows: list[str] = []
    for label, value in candidates:
        normalized = str(value or "").strip()
        if not normalized or normalized == "-":
            continue
        rows.append(f"| **{label}** | {normalized} |")
    return rows


def _normalize_route_flow_display(value: str) -> str:
    """
    커뮤니케이션 단계 문자열을 테이블 표시용으로 정규화한다.

    Args:
        value: 원본 단계 문자열(`from=>to%%from=>to` 또는 구버전 `||`)

    Returns:
        정규화된 단계 문자열
    """
    text = str(value or "").strip()
    if not text:
        return ""
    chunks = [item.strip() for item in re.split(r"\s*(?:%%|\|\|)\s*", text) if item and item.strip()]
    if not chunks:
        return ""
    return " ↠ ".join(chunks[:6])


def _normalize_people_display(value: str) -> str:
    """
    기본 정보(발신/수신) 값에서 표시용 사람 이름 목록을 정규화한다.

    Args:
        value: 원본 값

    Returns:
        정규화된 표시 문자열
    """
    text = str(value or "").strip()
    if not text or text == "-":
        return text
    tokens = [item.strip() for item in re.split(r"[;,\n]+", text) if item and item.strip()]
    names: list[str] = []
    for token in tokens:
        candidate = _extract_single_person_name(token=token)
        if candidate and candidate not in names:
            names.append(candidate)
    if not names:
        return text
    return ", ".join(names[:4]) + (" 외" if len(names) > 4 else "")


def _extract_single_person_name(token: str) -> str:
    """
    단일 토큰에서 사람 이름 후보를 추출한다.

    Args:
        token: 단일 수신자/발신자 토큰

    Returns:
        정규화된 이름 문자열
    """
    cleaned = re.sub(r"<[^>]*>", "", str(token or "")).strip()
    if not cleaned:
        return ""
    cleaned = cleaned.split("/", 1)[0].strip().strip("\"' ")
    cleaned = re.sub(r"\([^)]*\)", "", cleaned).strip()
    if not cleaned:
        return ""
    if re.fullmatch(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}", cleaned):
        return cleaned.split("@", 1)[0]
    cleaned = re.sub(r"(매니저|부장|차장|과장|대리|님)$", "", cleaned).strip()
    return cleaned


def _build_summary_lines_for_target(contract: LLMResponseContract, line_target: int) -> list[str]:
    """
    요청 줄 수를 최대한 충족하도록 요약 라인 후보를 합성한다.

    Args:
        contract: JSON 계약 객체
        line_target: 요청 줄 수

    Returns:
        합성된 요약 라인 목록
    """
    candidates: list[str] = []
    candidates.extend(sanitize_summary_lines(lines=list(contract.summary_lines)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.major_points)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.key_points)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.action_items)))
    candidates.extend(sanitize_summary_lines(lines=list(contract.required_actions)))
    if contract.core_issue:
        candidates.append(contract.core_issue)
    candidates.extend(extract_summary_lines(answer=contract.answer))

    normalized = _dedupe_lines(lines=sanitize_summary_lines(lines=candidates))
    if len(normalized) >= line_target:
        return normalized[:line_target]

    expanded = _expand_lines(lines=normalized, line_target=line_target)
    if len(expanded) >= line_target:
        return expanded[:line_target]

    while len(expanded) < line_target:
        expanded.append("추가 핵심 정보 확인 필요")
    return expanded[:line_target]


def _build_explicit_line_summary(contract: LLMResponseContract, line_target: int) -> list[str]:
    """
    명시 줄수 요약은 contract.summary_lines만 기반으로 엄격히 구성한다.

    Args:
        contract: JSON 계약 객체
        line_target: 요청 줄 수

    Returns:
        명시 줄수용 요약 라인 목록
    """
    base_lines = _dedupe_lines(lines=sanitize_summary_lines(lines=list(contract.summary_lines)))
    if len(base_lines) >= line_target:
        return base_lines[:line_target]

    supplements: list[str] = []
    supplements.extend(sanitize_summary_lines(lines=list(contract.major_points)))
    supplements.extend(sanitize_summary_lines(lines=list(contract.required_actions)))
    supplements.extend(sanitize_summary_lines(lines=list(contract.action_items)))
    supplements.extend(sanitize_summary_lines(lines=list(contract.key_points)))
    if contract.core_issue:
        supplements.append(contract.core_issue)
    if contract.one_line_summary:
        supplements.append(contract.one_line_summary)
    supplements.extend(extract_summary_lines(answer=contract.answer))

    merged = _dedupe_lines(lines=[*base_lines, *sanitize_summary_lines(lines=supplements)])
    while len(merged) < line_target:
        merged.append("추가 핵심 정보 확인 필요")
    return merged[:line_target]


def _expand_lines(lines: list[str], line_target: int) -> list[str]:
    """
    부족한 요약 라인을 headline/detail 분할로 확장한다.

    Args:
        lines: 기본 요약 라인 목록
        line_target: 요청 줄 수

    Returns:
        확장된 요약 라인 목록
    """
    expanded = list(lines)
    for line in lines:
        if len(expanded) >= line_target:
            break
        headline, detail = split_headline_and_detail(line=line)
        if detail and detail not in expanded:
            expanded.append(detail)
    return _dedupe_lines(lines=expanded)


def _dedupe_lines(lines: list[str]) -> list[str]:
    """
    라인 순서를 유지하며 중복을 제거한다.

    Args:
        lines: 라인 목록

    Returns:
        중복 제거 라인 목록
    """
    unique: list[str] = []
    for line in lines:
        text = str(line or "").strip()
        if not text:
            continue
        if text in unique:
            continue
        unique.append(text)
    return unique
