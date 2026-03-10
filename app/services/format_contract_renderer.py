from __future__ import annotations

from typing import Mapping

from app.models.response_contracts import LLMResponseContract
from app.services.format_policy_selector import FormatTemplateId

TECH_TOKENS: tuple[str, ...] = ("기술", "이슈", "오류", "장애", "보안", "api", "ssl")


def render_template_driven_contract(
    contract: LLMResponseContract,
    section_contract: Mapping[str, object] | None,
) -> str:
    """
    템플릿/섹션 계약 기반으로 contract 응답을 정형 포맷으로 렌더링한다.

    Args:
        contract: 파싱된 LLM 응답 계약
        section_contract: 템플릿 섹션 계약

    Returns:
        렌더링 문자열. 지원 템플릿이 아니거나 생성 실패 시 빈 문자열
    """
    if not isinstance(section_contract, Mapping):
        return ""
    template_id = str(section_contract.get("template_id") or "").strip().lower()
    if template_id not in {
        FormatTemplateId.CURRENT_MAIL_SUMMARY.value,
        FormatTemplateId.CURRENT_MAIL_SUMMARY_ISSUE.value,
    }:
        return ""
    section_ids = _extract_section_ids(section_contract=section_contract)
    return _render_current_mail_contract(contract=contract, section_ids=section_ids)


def _render_current_mail_contract(contract: LLMResponseContract, section_ids: set[str]) -> str:
    """
    현재메일 템플릿 계약을 섹션 ID 기준으로 렌더링한다.

    Args:
        contract: 파싱된 LLM 응답 계약
        section_ids: 활성 섹션 ID 집합

    Returns:
        렌더링 문자열
    """
    include_summary = (not section_ids) or ("summary" in section_ids) or ("major" in section_ids)
    include_tech = (not section_ids) or ("tech_issue" in section_ids)
    include_action = (not section_ids) or ("action" in section_ids)

    summary_lines = _pick_summary_lines(contract=contract) if include_summary else []
    tech_lines = _pick_tech_issue_lines(contract=contract) if include_tech else []
    action_lines = _pick_action_lines(contract=contract) if include_action else []

    if not summary_lines and not tech_lines and not action_lines:
        return ""

    rendered: list[str] = []
    if summary_lines:
        rendered.append("## 📌 주요 내용")
        for index, line in enumerate(summary_lines, start=1):
            rendered.append(f"{index}. {line}")
    if tech_lines:
        if rendered:
            rendered.append("")
        rendered.append("### 🛠 기술 이슈")
        for index, line in enumerate(tech_lines, start=1):
            rendered.append(f"{index}. {line}")
    if action_lines:
        if rendered:
            rendered.append("")
        rendered.append("### ✅ 조치 필요 사항")
        for index, line in enumerate(action_lines, start=1):
            rendered.append(f"{index}. {line}")
    return "\n".join(rendered).strip()


def _pick_summary_lines(contract: LLMResponseContract) -> list[str]:
    """
    contract에서 주요 요약 라인을 추출한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        요약 라인 목록
    """
    candidates = [
        str(contract.one_line_summary or "").strip(),
        str(contract.core_issue or "").strip(),
        *[str(item or "").strip() for item in contract.summary_lines],
        *[str(item or "").strip() for item in contract.major_points],
    ]
    return _dedupe_lines(lines=candidates)[:3]


def _pick_tech_issue_lines(contract: LLMResponseContract) -> list[str]:
    """
    contract에서 기술 이슈 성격의 라인을 추출한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        기술 이슈 라인 목록
    """
    candidates = [
        *[str(item or "").strip() for item in contract.major_points],
        *[str(item or "").strip() for item in contract.key_points],
        *[str(item or "").strip() for item in contract.summary_lines],
    ]
    filtered: list[str] = []
    for line in candidates:
        compact = line.replace(" ", "").lower()
        if compact and any(token in compact for token in TECH_TOKENS):
            filtered.append(line)
    return _dedupe_lines(lines=filtered)[:3]


def _pick_action_lines(contract: LLMResponseContract) -> list[str]:
    """
    contract에서 조치 라인을 추출한다.

    Args:
        contract: 파싱된 LLM 응답 계약

    Returns:
        조치 라인 목록
    """
    candidates = [
        *[str(item or "").strip() for item in contract.required_actions],
        *[str(item or "").strip() for item in contract.action_items],
    ]
    return _dedupe_lines(lines=candidates)[:3]


def _extract_section_ids(section_contract: Mapping[str, object]) -> set[str]:
    """
    섹션 계약에서 섹션 ID 집합을 추출한다.

    Args:
        section_contract: 템플릿 섹션 계약

    Returns:
        섹션 ID 집합
    """
    sections = section_contract.get("sections")
    if not isinstance(sections, list):
        return set()
    section_ids: set[str] = set()
    for item in sections:
        if not isinstance(item, Mapping):
            continue
        section_id = str(item.get("id") or "").strip().lower()
        if section_id:
            section_ids.add(section_id)
    return section_ids


def _dedupe_lines(lines: list[str]) -> list[str]:
    """
    줄 단위 텍스트 중복을 제거한다.

    Args:
        lines: 원본 라인 목록

    Returns:
        중복 제거된 라인 목록
    """
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        text = str(line or "").strip()
        key = text.lower()
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped
