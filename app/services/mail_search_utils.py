from __future__ import annotations

import hashlib
import math
import re
import time

from app.services.mail_text_utils import extract_sender_display_name

EMBEDDING_DIM = 256
RRF_K = 50
COMMON_QUERY_TOKENS = {
    "메일",
    "찾아",
    "찾아서",
    "찾아줘",
    "조회",
    "검색",
    "정리",
    "정리해줘",
    "요약",
    "요약해줘",
    "알려줘",
    "보여줘",
    "요청",
    "관련",
    "최근",
    "최근순",
    "이번",
    "지난",
    "현재",
    "현재메일",
    "중",
    "만",
    "에서",
    "해줘",
    "해",
    "줘",
}
PERSON_QUERY_STOPWORDS = {
    "현재",
    "관련",
    "메일",
    "이메일",
    "요약",
    "정리",
    "조회",
    "검색",
    "프로젝트",
    "일정",
    "보고서",
    "오류",
    "원인",
    "영향",
    "대응",
    "요청",
}
QUOTE_PATTERN = re.compile(r"[\"'“”‘’]\s*([^\"'“”‘’]{2,120}?)\s*[\"'“”‘’]")
PERSON_ANCHOR_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(r"([가-힣]{2,4})\s*관련"),
    re.compile(r"([가-힣]{2,4})\s*님"),
    re.compile(r"([가-힣]{2,4})\s*(?:에게|한테)"),
)


def normalize_limit(limit: int) -> int:
    """
    limit 입력값을 안전 범위로 정규화한다.

    Args:
        limit: 입력 limit

    Returns:
        정규화된 limit
    """
    if limit < 1:
        return 1
    if limit > 20:
        return 20
    return limit


def tokenize_for_search(text: str) -> list[str]:
    """
    검색 질의를 토큰 목록으로 분해한다.

    Args:
        text: 사용자 질의

    Returns:
        토큰 목록
    """
    return [token.strip().lower() for token in re.findall(r"[가-힣A-Za-z0-9]+", str(text or "")) if token.strip()]


def extract_meaningful_query_tokens(text: str) -> list[str]:
    """
    사용자 질의에서 검색 의미가 약한 공통 토큰을 제외한 키워드를 추출한다.

    Args:
        text: 사용자 질의

    Returns:
        의미 토큰 목록
    """
    tokens = tokenize_for_search(text=text)
    unique: list[str] = []
    for token in tokens:
        if token in COMMON_QUERY_TOKENS:
            continue
        if len(token) < 2:
            continue
        if token not in unique:
            unique.append(token)
    return unique


def extract_person_anchor_tokens(query: str) -> list[str]:
    """
    질의에서 인물 앵커(이름) 토큰을 추출한다.

    Args:
        query: 사용자 질의

    Returns:
        인물 앵커 토큰 목록
    """
    text = str(query or "").strip()
    if not text:
        return []
    anchors: list[str] = []
    for pattern in PERSON_ANCHOR_PATTERNS:
        for match in pattern.findall(text):
            token = str(match or "").strip()
            if not token or token in PERSON_QUERY_STOPWORDS:
                continue
            if token not in anchors:
                anchors.append(token)
    return anchors


def row_matches_person_anchors(row: "MailSearchResult", anchors: list[str]) -> bool:
    """
    검색 결과가 인물 앵커 토큰과 정합되는지 판별한다.

    Args:
        row: 검색 결과 메일
        anchors: 인물 앵커 토큰 목록

    Returns:
        인물 앵커 매칭 시 True
    """
    if not anchors:
        return True
    haystack = build_summary_zone(item=row).lower()
    return any(anchor.lower() in haystack for anchor in anchors)


def keyword_match_count(row: "MailSearchResult", keywords: list[str]) -> int:
    """
    검색 결과 한 건이 질의 핵심 키워드와 일치하는 개수를 계산한다.

    Args:
        row: 검색 결과 메일
        keywords: 핵심 키워드 목록

    Returns:
        일치 키워드 수
    """
    if not keywords:
        return 0
    haystack = build_summary_zone(item=row).lower()
    return sum(1 for keyword in keywords if keyword in haystack)


def min_keyword_hits_for_query(query: str) -> int:
    """
    질의 난이도(핵심 토큰 수)에 따라 최소 키워드 일치 개수를 계산한다.

    Args:
        query: 사용자 질의

    Returns:
        최소 키워드 일치 개수
    """
    meaningful_count = len(extract_meaningful_query_tokens(text=query))
    if meaningful_count >= 4:
        return 2
    if meaningful_count >= 1:
        return 1
    return 0


def extract_required_body_phrases(query: str) -> list[str]:
    """
    `본문에 'X' 포함` 형태 질의에서 본문 필수 포함 구문 목록을 추출한다.

    Args:
        query: 사용자 질의

    Returns:
        본문 필수 구문 목록
    """
    text = str(query or "")
    if "본문" not in text:
        return []
    if ("포함" not in text) and ("들어가" not in text):
        return []
    phrases: list[str] = []
    for match in QUOTE_PATTERN.findall(text):
        normalized = str(match or "").strip()
        if not normalized:
            continue
        if normalized not in phrases:
            phrases.append(normalized)
    return phrases


def has_required_body_phrases(row: "MailSearchResult", phrases: list[str]) -> bool:
    """
    메일 본문에 필수 구문이 모두 포함되는지 확인한다.

    Args:
        row: 검색 결과 메일
        phrases: 본문 필수 구문 목록

    Returns:
        모두 포함되면 True
    """
    if not phrases:
        return True
    body = str(row.body_text or "")
    lowered_body = body.lower()
    for phrase in phrases:
        normalized = str(phrase or "").strip()
        if not normalized:
            continue
        if normalized.lower() not in lowered_body:
            return False
    return True


def rerank_candidates(query: str, rows: list["MailSearchResult"]) -> list["MailSearchResult"]:
    """
    후보 목록을 키워드/벡터 점수 기반으로 재정렬한다.

    Args:
        query: 사용자 질의
        rows: 후보 목록

    Returns:
        재정렬된 목록
    """
    lexical_ranks = build_lexical_rank(rows=rows, query=query)
    semantic_ranks = build_semantic_rank(rows=rows, query=query)
    recency_ranks = {item.message_id: index + 1 for index, item in enumerate(rows)}
    scored: list[tuple[float, "MailSearchResult"]] = []
    for item in rows:
        message_id = item.message_id
        rank_score = (
            1.0 / (RRF_K + lexical_ranks.get(message_id, len(rows) + 1))
            + 1.0 / (RRF_K + semantic_ranks.get(message_id, len(rows) + 1))
            + 1.0 / (RRF_K + recency_ranks.get(message_id, len(rows) + 1))
        )
        scored.append((rank_score, item))
    scored.sort(key=lambda item: item[0], reverse=True)
    return [item[1] for item in scored]


def build_lexical_rank(rows: list["MailSearchResult"], query: str) -> dict[str, int]:
    """
    키워드 기반 점수 순위 맵을 계산한다.

    Args:
        rows: 후보 목록
        query: 사용자 질의

    Returns:
        message_id -> rank(1부터 시작)
    """
    tokens = tokenize_for_search(text=query)
    if not tokens:
        return {item.message_id: index + 1 for index, item in enumerate(rows)}
    scored: list[tuple[int, str]] = []
    for item in rows:
        summary_zone = build_summary_zone(item=item).lower()
        body_zone = str(item.body_text or "")[:400].lower()
        subject_zone = str(item.subject or "").lower()
        score = 0
        for token in tokens:
            if token in subject_zone:
                score += 4
            if token in summary_zone:
                score += 3
            elif token in body_zone:
                score += 1
        scored.append((score, item.message_id))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    return {message_id: index + 1 for index, (_, message_id) in enumerate(scored)}


def build_semantic_rank(rows: list["MailSearchResult"], query: str) -> dict[str, int]:
    """
    해시 임베딩 코사인 유사도 기반 순위 맵을 계산한다.

    Args:
        rows: 후보 목록
        query: 사용자 질의

    Returns:
        message_id -> rank(1부터 시작)
    """
    query_vector = build_hash_embedding(text=query)
    scored: list[tuple[float, str]] = []
    for item in rows:
        doc_text = build_summary_zone(item=item)
        doc_vector = build_hash_embedding(text=doc_text)
        similarity = cosine_similarity(left=query_vector, right=doc_vector)
        scored.append((similarity, item.message_id))
    scored.sort(key=lambda entry: entry[0], reverse=True)
    return {message_id: index + 1 for index, (_, message_id) in enumerate(scored)}


def build_hash_embedding(text: str, dim: int = EMBEDDING_DIM) -> list[float]:
    """
    토큰 해시 기반 임베딩 벡터를 생성한다.

    Args:
        text: 입력 텍스트
        dim: 벡터 차원 수

    Returns:
        정규화된 벡터
    """
    vector = [0.0] * dim
    tokens = tokenize_for_search(text=text)
    for token in tokens:
        digest = hashlib.md5(token.encode("utf-8")).hexdigest()
        index = int(digest[:8], 16) % dim
        sign = -1.0 if int(digest[8:16], 16) % 2 else 1.0
        vector[index] += sign
    norm = math.sqrt(sum(value * value for value in vector))
    if norm == 0:
        return vector
    return [value / norm for value in vector]


def cosine_similarity(left: list[float], right: list[float]) -> float:
    """
    두 벡터의 코사인 유사도를 계산한다.

    Args:
        left: 좌측 벡터
        right: 우측 벡터

    Returns:
        코사인 유사도 값
    """
    if not left or not right:
        return 0.0
    size = min(len(left), len(right))
    return sum(left[index] * right[index] for index in range(size))


def to_result_payload(row: "MailSearchResult") -> dict[str, str]:
    """
    UI/에이전트 공용 검색 결과 payload를 생성한다.

    Args:
        row: 검색 결과 모델

    Returns:
        직렬화 가능한 결과 사전
    """
    snippet = build_result_snippet(row=row)
    return {
        "message_id": row.message_id,
        "subject": row.subject or "제목 없음",
        "received_date": row.received_date or "-",
        "from_address": row.from_address or "-",
        "sender_names": extract_sender_display_name(from_address=row.from_address),
        "snippet": snippet,
        "summary_text": str(row.summary_text or "").strip(),
        "web_link": row.web_link,
    }


def build_body_snippet(text: str, max_chars: int = 180) -> str:
    """
    본문 미리보기(snippet) 문자열을 생성한다.

    Args:
        text: 본문 텍스트
        max_chars: 최대 길이

    Returns:
        미리보기 문자열
    """
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 1].rstrip() + "…"


def build_result_snippet(row: "MailSearchResult") -> str:
    """
    검색 결과 노출용 snippet을 생성한다.

    Args:
        row: 검색 결과 모델

    Returns:
        요약 우선 snippet 문자열
    """
    summary_text = str(row.summary_text or "").strip()
    if summary_text:
        return build_body_snippet(text=summary_text, max_chars=180)
    return build_body_snippet(text=row.body_text, max_chars=180)


def build_summary_zone(item: "MailSearchResult") -> str:
    """
    summary-first 검색을 위한 문서 표현 문자열을 생성한다.

    Args:
        item: 검색 후보 메일

    Returns:
        요약/제목/발신자 중심 텍스트
    """
    summary_text = str(item.summary_text or "").strip()
    compact_body = str(item.body_text or "")[:600]
    return f"{item.subject}\n{item.from_address}\n{summary_text}\n{compact_body}"


def build_aggregated_summary(results: list[dict[str, str]], line_target: int) -> list[str]:
    """
    조회 결과 상위 메일들의 저장된 summary만으로 통합 요약 라인을 생성한다.

    Args:
        results: 직렬화된 검색 결과 목록
        line_target: 목표 줄 수

    Returns:
        통합 요약 라인 목록(메일당 최대 1줄)
    """
    lines: list[str] = []
    for item in results:
        candidate = str(item.get("summary_text") or "").strip()
        if not candidate:
            continue
        normalized = normalize_summary_candidate(candidate)
        if not normalized:
            continue
        if normalized in lines:
            continue
        lines.append(normalized)
        if len(lines) >= line_target:
            break
    if lines:
        return lines
    return ["저장된 메일 요약(summary)이 없어 주요 내용을 표시하지 못했습니다."]


def normalize_summary_candidate(text: str) -> str:
    """
    통합 요약 후보 문장을 1줄 요약 형식으로 정규화한다.

    Args:
        text: 원본 요약 후보 텍스트

    Returns:
        정규화된 단일 라인
    """
    normalized = re.sub(r"\s+", " ", str(text or "")).strip()
    normalized = re.sub(r"^[\-\*•\d\)\.\s]+", "", normalized).strip()
    normalized = re.sub(r"\s+-\s+.*$", "", normalized).strip()
    if not normalized:
        return ""
    if len(normalized) > 110:
        return normalized[:109].rstrip() + "…"
    return normalized


def elapsed_ms(started_at: float) -> float:
    """
    시작 시각 기준 경과 시간을 ms 단위로 반환한다.

    Args:
        started_at: perf_counter 시작 시각

    Returns:
        경과 밀리초
    """
    return round((time.perf_counter() - started_at) * 1000.0, 1)
