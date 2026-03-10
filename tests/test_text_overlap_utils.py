from app.services.text_overlap_utils import (
    extract_overlap_tokens,
    normalize_compare_text,
    token_overlap_score,
)


def test_extract_overlap_tokens_filters_stop_words() -> None:
    tokens = extract_overlap_tokens("현재 내용 검토 요청 API 오류 확인")
    assert "api" in tokens
    assert "오류" in tokens
    assert "현재" not in tokens
    assert "검토" not in tokens


def test_token_overlap_score_returns_positive_overlap() -> None:
    base = set(extract_overlap_tokens("cloud pc api 오류"))
    score = token_overlap_score(base, "cloud pc 연동 api 장애")
    assert score > 0.0


def test_normalize_compare_text_keeps_alnum_korean_only() -> None:
    normalized = normalize_compare_text("M365 프로젝트 - API#오류(긴급)!")
    assert normalized == "m365프로젝트api오류긴급"
