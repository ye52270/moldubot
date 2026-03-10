from __future__ import annotations

import re
from typing import Any

from app.services.text_overlap_utils import extract_overlap_tokens, token_overlap_score

MIN_ARTIFACT_LINE_LENGTH = 8
MAX_ARTIFACT_LINE_LENGTH = 280
GENERIC_VALUE_TOKENS: tuple[str, ...] = (
    "query",
    "쿼리",
    "filter",
    "dn",
    "cn=",
    "dc=",
    "objectclass",
    "ldap",
    "ou",
)
GENERIC_OPERATOR_PATTERNS: tuple[str, ...] = (
    r"[<>=*]",
    r"\b(select|where|from)\b",
    r"[()\\[\]{}]",
)


def extract_query_artifact_candidates(mail_context: dict[str, Any]) -> list[str]:
    """
    메일 컨텍스트에서 쿼리/명령/식별 구문 후보 라인을 추출한다.

    Args:
        mail_context: tool payload의 mail_context

    Returns:
        후보 문자열 목록
    """
    raw_blocks = (
        str(mail_context.get("body_code_excerpt") or ""),
        str(mail_context.get("body_excerpt") or ""),
        str(mail_context.get("body_preview") or ""),
    )
    candidates: list[str] = []
    for block in raw_blocks:
        if not block:
            continue
        for line in str(block).splitlines():
            normalized = normalize_artifact_candidate_line(line=line)
            if not normalized:
                continue
            if not looks_like_query_artifact_line(line=normalized):
                continue
            if normalized in candidates:
                continue
            candidates.append(normalized)
    return candidates


def normalize_artifact_candidate_line(line: str) -> str:
    """
    artifact 후보 라인을 비교 가능한 형태로 정규화한다.

    Args:
        line: 원본 라인 문자열

    Returns:
        정규화된 라인. 유효하지 않으면 빈 문자열
    """
    text = " ".join(str(line or "").replace("\t", " ").split())
    if not text:
        return ""
    if len(text) < MIN_ARTIFACT_LINE_LENGTH:
        return ""
    if len(text) > MAX_ARTIFACT_LINE_LENGTH:
        return ""
    return text


def looks_like_query_artifact_line(line: str) -> bool:
    """
    라인이 쿼리/명령/식별 구문인지 판별한다.

    Args:
        line: 정규화된 후보 라인

    Returns:
        구문 후보면 True
    """
    lowered = str(line or "").lower()
    if any(token in lowered for token in GENERIC_VALUE_TOKENS):
        return True
    return any(re.search(pattern, lowered, flags=re.IGNORECASE) for pattern in GENERIC_OPERATOR_PATTERNS)


def rank_query_artifact_candidates(user_message: str, candidates: list[str]) -> list[str]:
    """
    사용자 질의와의 토큰 겹침으로 artifact 후보 우선순위를 계산한다.

    Args:
        user_message: 사용자 입력 원문
        candidates: 후보 문자열 목록

    Returns:
        우선순위가 적용된 후보 목록
    """
    base_tokens = set(extract_overlap_tokens(text=user_message))
    if not candidates:
        return []
    scored = [
        (token_overlap_score(point_tokens=base_tokens, candidate=item), index, item)
        for index, item in enumerate(candidates)
    ]
    scored.sort(key=lambda row: (-row[0], row[1]))
    return [item for _, _, item in scored]
