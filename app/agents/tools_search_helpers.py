from __future__ import annotations

import re
from typing import Any

from app.services.mail_search_service import MailSearchService

TECH_ISSUE_FANOUT_MAX_QUERIES = 6
TECH_ISSUE_QUERY_TOKENS = {"장애", "오류", "보안", "api", "ssl", "긴급", "차단"}


def is_tech_issue_query_text(query: str) -> bool:
    """
    질의가 기술 이슈 축 검색인지 판별한다.

    Args:
        query: 원본 질의

    Returns:
        기술 이슈 검색이면 True
    """
    normalized = str(query or "").strip().lower()
    if not normalized:
        return False
    if "기술" in normalized and "이슈" in normalized:
        return True
    if " or " in normalized:
        return any(token in normalized for token in TECH_ISSUE_QUERY_TOKENS)
    token_hits = sum(1 for token in TECH_ISSUE_QUERY_TOKENS if token in normalized)
    return token_hits >= 1


def apply_scope_to_query(query: str, contract: dict[str, str]) -> str:
    """
    scope 계약에 따라 검색 질의를 보정한다.

    Args:
        query: 원본 검색 질의
        contract: scope 계약 사전

    Returns:
        보정된 질의
    """
    normalized_query = str(query or "").strip()
    if not normalized_query:
        return normalized_query
    anchor_query = str(contract.get("anchor_query") or "").strip()
    if not anchor_query:
        return normalized_query
    if anchor_query.lower() in normalized_query.lower():
        return normalized_query
    if is_tech_issue_query_text(normalized_query):
        return f"{anchor_query} {normalized_query}"
    return normalized_query


def build_scope_blocked_payload(reason: str, query: str) -> dict[str, Any]:
    """
    scope 위반 시 반환할 표준 실패 payload를 생성한다.

    Args:
        reason: 실패 사유
        query: 검색 질의

    Returns:
        mail_search 실패 payload
    """
    return {
        "action": "mail_search",
        "status": "failed",
        "reason": reason,
        "query": str(query or "").strip(),
        "results": [],
        "count": 0,
        "aggregated_summary": [],
        "query_summaries": [],
    }


def should_fanout_tech_issue_query(query: str) -> bool:
    """
    기술 이슈 키워드 나열형 질의를 분할 검색 대상으로 판별한다.

    Args:
        query: 원본 검색 질의

    Returns:
        분할 검색 필요 여부
    """
    raw = str(query or "").strip()
    if "," not in raw:
        return False
    keywords = extract_fanout_keywords(query=raw)
    if len(keywords) < 2:
        return False
    return all(item in TECH_ISSUE_QUERY_TOKENS for item in keywords)


def extract_fanout_keywords(query: str) -> list[str]:
    """
    콤마/구분자 기반 질의에서 키워드 목록을 추출한다.

    Args:
        query: 원본 검색 질의

    Returns:
        정제된 키워드 목록
    """
    normalized = str(query or "").replace("/", ",").replace("|", ",")
    parts = [part.strip().lower() for part in re.split(r"[,\n]+", normalized)]
    keywords: list[str] = []
    for part in parts:
        if not part:
            continue
        if part in keywords:
            continue
        keywords.append(part)
        if len(keywords) >= TECH_ISSUE_FANOUT_MAX_QUERIES:
            break
    return keywords


def search_mails_with_query_fanout(
    query: str,
    person: str,
    start_date: str,
    end_date: str,
    limit: int,
    search_service: MailSearchService,
) -> dict[str, Any]:
    """
    분할 키워드 질의를 다중 검색으로 실행한 뒤 단일 payload로 병합한다.

    Args:
        query: 원본 검색 질의
        person: 사람명 필터
        start_date: 시작일
        end_date: 종료일
        limit: 반환 개수
        search_service: 메일 검색 서비스

    Returns:
        병합된 `mail_search` payload
    """
    keywords = extract_fanout_keywords(query=query)
    merged_results: list[dict[str, Any]] = []
    merged_summary: list[str] = []
    query_summaries: list[dict[str, Any]] = []
    seen_message_ids: set[str] = set()
    for keyword in keywords:
        payload = search_service.search(
            query=keyword,
            person=person,
            start_date=start_date,
            end_date=end_date,
            limit=limit,
        )
        lines: list[str] = []
        aggregated = payload.get("aggregated_summary")
        if isinstance(aggregated, list):
            for line in aggregated:
                text = str(line or "").strip()
                if text:
                    merged_summary.append(text)
                    lines.append(text)
        results = payload.get("results")
        if isinstance(results, list):
            for row in results:
                if not isinstance(row, dict):
                    continue
                message_id = str(row.get("message_id") or "").strip()
                if message_id and message_id in seen_message_ids:
                    continue
                if message_id:
                    seen_message_ids.add(message_id)
                merged_results.append(row)
                summary_text = str(row.get("summary_text") or "").strip()
                if summary_text:
                    lines.append(summary_text)
        if lines:
            deduped_lines: list[str] = []
            seen_line_keys: set[str] = set()
            for line in lines:
                key = line.lower()
                if key in seen_line_keys:
                    continue
                seen_line_keys.add(key)
                deduped_lines.append(line)
                if len(deduped_lines) >= 2:
                    break
            query_summaries.append({"query": keyword, "lines": deduped_lines})
    normalized_limit = max(1, int(limit or 5))
    return {
        "action": "mail_search",
        "status": "completed",
        "query": query,
        "person": person,
        "start_date": start_date,
        "end_date": end_date,
        "results": merged_results[:normalized_limit],
        "count": min(len(merged_results), normalized_limit),
        "aggregated_summary": merged_summary[:5],
        "query_summaries": query_summaries,
    }
