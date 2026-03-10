from __future__ import annotations

import re
from typing import Any, Mapping

from app.services.answer_postprocessor_mail_search_utils import (
    build_markdown_link,
    normalize_mail_search_summary_text,
    normalize_received_date,
    resolve_mail_search_summary_from_db,
)


def render_mail_search_digest_from_db(
    tool_payload: dict[str, Any],
    line_target: int = 3,
    section_contract: Mapping[str, object] | None = None,
) -> str:
    """
    mail_search 결과의 DB summary_text/aggregated_summary만 사용해 간결 요약을 렌더링한다.

    Args:
        tool_payload: 직전 tool payload
        line_target: 최대 요약 라인 수
        section_contract: 섹션 노출 계약 정보

    Returns:
        `## 📌 주요 내용` 요약 문자열. 구성 실패 시 빈 문자열
    """
    max_lines = max(2, min(int(line_target or 3), 3))
    lines = collect_mail_search_digest_lines(tool_payload=tool_payload, max_lines=max_lines)
    major_lines, tech_lines = split_mail_search_digest_sections(tool_payload=tool_payload, digest_lines=lines)
    section_ids = _resolve_section_ids(section_contract=section_contract)
    include_major = (not section_ids) or ("major" in section_ids)
    include_tech = (not section_ids) or ("tech_issue" in section_ids)
    include_evidence = (not section_ids) or ("evidence" in section_ids)

    if not include_major:
        major_lines = []
    if not include_tech:
        tech_lines = []
    if not major_lines and not tech_lines:
        return ""

    rendered = ["## 📌 주요 내용"]
    if include_major:
        for index, line in enumerate(major_lines, start=1):
            rendered.append(f"{index}. {line}")
    if include_tech and tech_lines:
        rendered.extend(["", "### 🛠 기술 이슈"])
        for index, line in enumerate(tech_lines, start=1):
            rendered.append(f"{index}. {line}")

    evidence_lines = render_mail_search_evidence_section(tool_payload=tool_payload) if include_evidence else []
    if include_evidence and evidence_lines:
        rendered.extend(["", *evidence_lines])
    return "\n".join(rendered).strip()


def collect_mail_search_digest_lines(tool_payload: dict[str, Any], max_lines: int = 3) -> list[str]:
    """
    메일 검색 payload에서 요약용 핵심 라인을 수집한다.

    Args:
        tool_payload: 직전 tool payload
        max_lines: 최대 반환 라인 수

    Returns:
        정제된 요약 라인 목록
    """
    target = max(1, min(int(max_lines or 3), 3))
    raw_candidates: list[str] = []

    aggregated = tool_payload.get("aggregated_summary")
    if isinstance(aggregated, list):
        for item in aggregated:
            normalized = normalize_mail_search_summary_text(item)
            if normalized:
                raw_candidates.append(normalized)

    results = tool_payload.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            normalized = resolve_mail_search_summary_from_db(item)
            if normalized:
                raw_candidates.append(normalized)

    deduped: list[str] = []
    seen: set[str] = set()
    for candidate in raw_candidates:
        normalized_key = re.sub(r"\s+", " ", str(candidate or "").strip().lower())
        if not normalized_key or normalized_key in seen:
            continue
        seen.add(normalized_key)
        deduped.append(candidate)
        if len(deduped) >= target:
            break
    return deduped


def split_mail_search_digest_sections(
    tool_payload: dict[str, Any],
    digest_lines: list[str],
) -> tuple[list[str], list[str]]:
    """
    digest 라인을 일반 주요내용/기술이슈 섹션으로 분리한다.

    Args:
        tool_payload: 직전 tool payload
        digest_lines: 수집된 digest 라인

    Returns:
        (주요내용 라인, 기술이슈 라인)
    """
    query_summaries = tool_payload.get("query_summaries")
    if isinstance(query_summaries, list):
        major_lines: list[str] = []
        tech_lines: list[str] = []
        for row in query_summaries:
            if not isinstance(row, dict):
                continue
            query = str(row.get("query") or "").strip().lower()
            lines = row.get("lines")
            if not isinstance(lines, list):
                continue
            normalized_lines = [normalize_mail_search_summary_text(item) for item in lines]
            normalized_lines = [line for line in normalized_lines if line and not _is_internal_fallback_line(line)]
            if not normalized_lines:
                continue
            if _is_tech_query(query=query):
                tech_lines.extend(normalized_lines)
            else:
                major_lines.extend(normalized_lines)
        major_lines = _dedupe_lines(lines=major_lines)[:3]
        tech_lines = _dedupe_lines(lines=tech_lines)[:3]
        if major_lines or tech_lines:
            return (major_lines, tech_lines)

    major_fallback: list[str] = []
    tech_fallback: list[str] = []
    for line in digest_lines:
        if _looks_like_tech_issue_line(line=line):
            tech_fallback.append(line)
        else:
            major_fallback.append(line)
    if not major_fallback and tech_fallback:
        major_fallback = tech_fallback[:1]
        tech_fallback = tech_fallback[1:]
    return (_dedupe_lines(lines=major_fallback)[:3], _dedupe_lines(lines=tech_fallback)[:3])


def render_mail_search_evidence_section(tool_payload: dict[str, Any]) -> list[str]:
    """
    조회 결과를 `근거 메일` 섹션 라인으로 렌더링한다.

    Args:
        tool_payload: 직전 tool payload

    Returns:
        근거 메일 섹션 markdown 라인 목록
    """
    results = tool_payload.get("results")
    if not isinstance(results, list) or not results:
        return []

    lines = ["### 📬 근거 메일"]
    seen: set[str] = set()
    count = 0
    for item in results:
        if not isinstance(item, dict):
            continue
        subject = str(item.get("subject") or "제목 없음").strip() or "제목 없음"
        message_id = str(item.get("message_id") or "").strip()
        web_link = str(item.get("web_link") or "").strip()
        dedupe_key = message_id or subject
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        received_date = normalize_received_date(item.get("received_date"))
        sender = str(item.get("sender_names") or item.get("from_address") or "-").strip() or "-"
        title = build_markdown_link(text=subject, url=web_link, message_id=message_id) if web_link else subject
        lines.append(f"- {title} ({received_date} · {sender})")
        count += 1
        if count >= 5:
            break
    return lines if count else []


def _resolve_section_ids(section_contract: Mapping[str, object] | None) -> set[str]:
    """
    섹션 계약에서 섹션 id 집합을 추출한다.

    Args:
        section_contract: section contract dict

    Returns:
        섹션 id 집합
    """
    if not isinstance(section_contract, Mapping):
        return set()
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


def _is_tech_query(query: str) -> bool:
    """쿼리 문자열이 기술 이슈 성격인지 판별한다."""
    compact = str(query or "").replace(" ", "").lower()
    if not compact:
        return False
    tokens = ("기술", "이슈", "오류", "장애", "api", "ssl", "보안")
    return any(token in compact for token in tokens)


def _is_internal_fallback_line(line: str) -> bool:
    """내부 fallback 문구 노출 여부를 판별한다."""
    normalized = re.sub(r"\s+", " ", str(line or "").strip().lower())
    return "저장된 메일 요약(summary)이 없어 주요 내용을 표시하지 못했습니다." in normalized


def _looks_like_tech_issue_line(line: str) -> bool:
    """요약 라인이 기술 이슈 성격인지 판별한다."""
    compact = str(line or "").replace(" ", "").lower()
    if not compact:
        return False
    tokens = ("기술", "이슈", "오류", "장애", "api", "ssl", "보안", "긴급")
    return any(token in compact for token in tokens)


def _dedupe_lines(lines: list[str]) -> list[str]:
    """공백/대소문자만 다른 중복 라인을 제거한다."""
    deduped: list[str] = []
    seen: set[str] = set()
    for line in lines:
        normalized = re.sub(r"\s+", " ", str(line or "").strip().lower())
        if not normalized or normalized in seen:
            continue
        seen.add(normalized)
        deduped.append(str(line or "").strip())
    return deduped
