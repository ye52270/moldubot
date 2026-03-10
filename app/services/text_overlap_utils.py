from __future__ import annotations

import re

DEFAULT_KO_EN_STOP_WORDS = {
    "현재",
    "관련",
    "내용",
    "필요",
    "검토",
    "요청",
    "확인",
    "및",
    "에서",
    "으로",
    "대한",
}


def extract_overlap_tokens(text: str, stop_words: set[str] | None = None) -> list[str]:
    """
    중복/불용어를 제외한 비교 토큰을 추출한다.

    Args:
        text: 원문 텍스트
        stop_words: 제외할 불용어 집합. 미지정 시 기본 집합 사용

    Returns:
        토큰 목록
    """
    candidates = re.findall(r"[A-Za-z0-9가-힣]{2,}", str(text or "").lower())
    excluded = stop_words if stop_words is not None else DEFAULT_KO_EN_STOP_WORDS
    return [item for item in candidates if item not in excluded]


def token_overlap_score(point_tokens: set[str], candidate: str) -> float:
    """
    기준 토큰 집합과 후보 문자열의 겹침 점수를 계산한다.

    Args:
        point_tokens: 기준 토큰 집합
        candidate: 후보 문자열

    Returns:
        겹침 점수(0~1)
    """
    candidate_tokens = set(extract_overlap_tokens(text=candidate))
    if not point_tokens or not candidate_tokens:
        return 0.0
    overlap = point_tokens.intersection(candidate_tokens)
    return len(overlap) / max(len(point_tokens), 1)


def normalize_compare_text(text: str) -> str:
    """
    비교용 문자열을 정규화한다.

    Args:
        text: 원문 문자열

    Returns:
        정규화된 문자열
    """
    return re.sub(r"[^a-z0-9가-힣]", "", str(text or "").lower())
