from __future__ import annotations

import re


def looks_like_org_signature(text: str) -> bool:
    """
    조직/직함만 나열된 서명성 문장인지 판별한다.

    Args:
        text: 검사할 텍스트

    Returns:
        서명성 문장이면 True
    """
    normalized = str(text or "").strip()
    if not normalized:
        return True
    slash_count = normalized.count("/")
    if slash_count < 2:
        return False
    if any(keyword in normalized for keyword in ("요청", "문의", "조치", "확인", "불가", "필요")):
        return False
    return len(normalized) <= 60


def is_near_duplicate(existing: list[str], candidate: str) -> bool:
    """
    기존 라인과 의미가 유사한 후보를 중복으로 판정한다.

    Args:
        existing: 기존 라인 목록
        candidate: 신규 후보 라인

    Returns:
        근접 중복이면 True
    """
    normalized_candidate = normalize_line_for_similarity(text=candidate)
    for item in existing:
        normalized_item = normalize_line_for_similarity(text=item)
        if not normalized_item or not normalized_candidate:
            continue
        if normalized_item == normalized_candidate:
            return True
        if normalized_item in normalized_candidate or normalized_candidate in normalized_item:
            return True
    return False


def normalize_line_for_similarity(text: str) -> str:
    """
    문장 유사도 비교를 위한 정규화 문자열을 생성한다.

    Args:
        text: 원본 텍스트

    Returns:
        정규화 문자열
    """
    normalized = str(text or "").lower()
    normalized = re.sub(r"[*_`]", "", normalized)
    normalized = re.sub(r"[-–—:;,.()\\[\\]]", " ", normalized)
    normalized = re.sub(r"\s+", " ", normalized).strip()
    return normalized
