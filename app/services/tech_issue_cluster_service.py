from __future__ import annotations

import re
from typing import Any

from app.services.tech_issue_taxonomy import (
    TECH_ISSUE_TYPE_MAP,
    TECH_KEYWORD_ALLOWLIST,
    TECH_KEYWORD_PATTERN,
)
from app.services.text_overlap_utils import (
    extract_overlap_tokens,
    normalize_compare_text,
    token_overlap_score,
)


def build_tech_issue_clusters(
    tool_payload: dict[str, Any],
    evidence_mails: list[dict[str, str]],
) -> list[dict[str, Any]]:
    """
    tool payload에서 기술 이슈 클러스터(키워드/유형/근거메일)를 생성한다.

    Args:
        tool_payload: 마지막 tool payload
        evidence_mails: 근거메일 목록

    Returns:
        기술 이슈 클러스터 목록
    """
    lines = _extract_tech_issue_lines(tool_payload=tool_payload)
    if not lines:
        return []
    results = tool_payload.get("results") if isinstance(tool_payload, dict) else []
    result_rows = results if isinstance(results, list) else []
    clusters: list[dict[str, Any]] = []
    for line in lines[:4]:
        keywords = _extract_tech_keywords(line=line)
        issue_type = _resolve_tech_issue_type(keywords=keywords)
        related = _select_related_mails_for_issue(
            issue_line=line,
            keywords=keywords,
            results=result_rows,
            fallback_mails=evidence_mails,
        )
        clusters.append(
            {
                "summary": line,
                "keywords": keywords,
                "issue_type": issue_type,
                "related_mails": related,
            }
        )
    return clusters


def _extract_tech_issue_lines(tool_payload: dict[str, Any]) -> list[str]:
    """
    payload에서 기술 이슈 문장 목록을 추출한다.

    Args:
        tool_payload: 마지막 tool payload

    Returns:
        기술 이슈 문장 목록
    """
    if not isinstance(tool_payload, dict):
        return []
    query_summaries = tool_payload.get("query_summaries")
    lines: list[str] = []
    if isinstance(query_summaries, list):
        for row in query_summaries:
            if not isinstance(row, dict):
                continue
            query = str(row.get("query") or "").strip()
            if not _is_tech_query_text(query=query):
                continue
            row_lines = row.get("lines")
            if not isinstance(row_lines, list):
                continue
            for item in row_lines:
                text = str(item or "").strip()
                if text and "근거를 찾지 못했습니다" not in text:
                    lines.append(text)
    if lines:
        return _dedupe_texts(values=lines)[:4]
    aggregated = tool_payload.get("aggregated_summary")
    if isinstance(aggregated, list):
        fallback = [str(item or "").strip() for item in aggregated if str(item or "").strip()]
        tech_only = [line for line in fallback if _looks_like_tech_text(text=line)]
        return _dedupe_texts(values=tech_only)[:3]
    return []


def _is_tech_query_text(query: str) -> bool:
    """
    쿼리가 기술 이슈 축인지 판별한다.

    Args:
        query: 쿼리 문자열

    Returns:
        기술 이슈 축이면 True
    """
    normalized = normalize_compare_text(text=query)
    if not normalized:
        return False
    return any(token in normalized for token in ("기술", "이슈", "오류", "장애", "api", "ssl", "보안"))


def _looks_like_tech_text(text: str) -> bool:
    """
    문장이 기술 이슈 성격인지 판별한다.

    Args:
        text: 문장 문자열

    Returns:
        기술 이슈 성격이면 True
    """
    normalized = normalize_compare_text(text=text)
    if not normalized:
        return False
    return any(token in normalized for token in ("오류", "장애", "api", "ssl", "보안", "차단", "인증", "연동"))


def _extract_tech_keywords(line: str) -> list[str]:
    """
    기술 이슈 문장에서 키워드를 추출한다.

    Args:
        line: 기술 이슈 문장

    Returns:
        키워드 목록(최대 5개)
    """
    tokens = TECH_KEYWORD_PATTERN.findall(str(line or "").lower())
    keywords: list[str] = []
    for token in tokens:
        normalized = str(token or "").strip().lower()
        if not normalized:
            continue
        if normalized not in TECH_KEYWORD_ALLOWLIST:
            continue
        if normalized in keywords:
            continue
        keywords.append(normalized.upper() if normalized in {"api", "ssl", "gpo", "eai", "sso", "m365"} else normalized)
        if len(keywords) >= 5:
            break
    return keywords


def _resolve_tech_issue_type(keywords: list[str]) -> str:
    """
    키워드 기반 기술 이슈 유형 라벨을 반환한다.

    Args:
        keywords: 키워드 목록

    Returns:
        유형 라벨
    """
    for keyword in keywords:
        normalized = str(keyword or "").strip().lower()
        mapped = TECH_ISSUE_TYPE_MAP.get(normalized)
        if mapped:
            return mapped
    return "기술 검토 필요"


def _select_related_mails_for_issue(
    issue_line: str,
    keywords: list[str],
    results: list[Any],
    fallback_mails: list[dict[str, str]],
) -> list[dict[str, str]]:
    """
    기술 이슈 문장과 연관된 메일 근거를 선택한다.

    Args:
        issue_line: 기술 이슈 문장
        keywords: 추출 키워드
        results: tool payload results
        fallback_mails: 기본 근거메일 목록

    Returns:
        관련 메일 목록(최대 3건)
    """
    selected: list[dict[str, str]] = []
    normalized_keywords = [str(item or "").strip().lower() for item in keywords if str(item or "").strip()]
    issue_tokens = set(extract_overlap_tokens(text=issue_line))
    for item in results:
        if not isinstance(item, dict):
            continue
        haystack = " ".join(
            [
                str(item.get("subject") or ""),
                str(item.get("summary_text") or ""),
                str(item.get("snippet") or ""),
            ]
        ).lower()
        if not haystack:
            continue
        keyword_match = any(token in haystack for token in normalized_keywords)
        overlap_score = token_overlap_score(point_tokens=issue_tokens, candidate=haystack)
        if not keyword_match and overlap_score < 0.12:
            continue
        selected.append(
            {
                "message_id": str(item.get("message_id") or "").strip(),
                "subject": str(item.get("subject") or "").strip() or "제목 없음",
                "received_date": str(item.get("received_date") or "").strip() or "-",
                "sender_names": str(item.get("sender_names") or item.get("from_address") or "-").strip() or "-",
                "web_link": str(item.get("web_link") or "").strip(),
                "snippet": str(item.get("summary_text") or item.get("snippet") or "").strip()[:220],
            }
        )
        if len(selected) >= 3:
            break
    if selected:
        return selected
    return [dict(item) for item in fallback_mails[:2] if isinstance(item, dict)]


def _dedupe_texts(values: list[str]) -> list[str]:
    """
    텍스트 리스트에서 공백/대소문자 기준 중복을 제거한다.

    Args:
        values: 텍스트 목록

    Returns:
        중복 제거 텍스트 목록
    """
    deduped: list[str] = []
    seen: set[str] = set()
    for item in values:
        text = str(item or "").strip()
        key = re.sub(r"\s+", " ", text.lower())
        if not text or key in seen:
            continue
        seen.add(key)
        deduped.append(text)
    return deduped
