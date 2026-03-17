from __future__ import annotations

import re
from typing import Any

from app.services.mail_search_utils import keyword_match_count


def should_reject_top_result_for_high_specific_query(
    query_keywords: list[str],
    top_row: Any,
) -> bool:
    """고특이도 질의에서 상위 1건의 키워드 일치가 낮으면 결과를 거부한다."""
    keyword_count = len(query_keywords)
    if keyword_count < 5:
        return False
    top_hits = keyword_match_count(row=top_row, keywords=query_keywords)
    required_hits = 4 if keyword_count >= 6 else 3
    if top_hits >= required_hits:
        return False
    if has_identifier_anchor_match(query_keywords=query_keywords, top_row=top_row):
        return False
    return True


def has_identifier_anchor_match(query_keywords: list[str], top_row: Any) -> bool:
    """질의 내 식별자 성격 토큰이 상위 메일에 존재하는지 확인한다."""
    anchor_tokens = [token for token in query_keywords if is_identifier_token(token)]
    if not anchor_tokens:
        return False
    haystack = " ".join(
        [
            str(getattr(top_row, "subject", "") or ""),
            str(getattr(top_row, "summary_text", "") or ""),
            str(getattr(top_row, "body_text", "") or ""),
        ]
    ).lower()
    return any(token in haystack for token in anchor_tokens)


def is_identifier_token(token: str) -> bool:
    """식별자 성격 토큰(영문/숫자 포함)인지 판별한다."""
    normalized = str(token or "").strip().lower()
    if len(normalized) < 2:
        return False
    return bool(re.search(r"[a-z0-9]", normalized))
