from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass
from pathlib import Path
import re

from app.core.logging_config import get_logger
from app.services.mail_search_utils import (
    build_aggregated_summary,
    elapsed_ms,
    extract_person_anchor_tokens,
    extract_meaningful_query_tokens,
    extract_required_body_phrases,
    has_required_body_phrases,
    keyword_match_count,
    min_keyword_hits_for_query,
    normalize_limit,
    rerank_candidates,
    row_matches_person_anchors,
    to_result_payload,
    tokenize_for_search,
)

logger = get_logger(__name__)
PREFERRED_OUTLOOK_LINK_COLUMNS: tuple[str, ...] = (
    "outlook_link",
    "outlook_deep_link",
    "outlook_uri",
    "desktop_link",
    "native_link",
    "open_link",
)


@dataclass
class MailSearchResult:
    """
    메일 검색 결과 데이터 모델.

    Attributes:
        message_id: 메시지 식별자
        subject: 메일 제목
        from_address: 발신자 원문
        received_date: 수신 일시
        body_text: 본문 텍스트
        summary_text: 메일 단건 요약 텍스트
        web_link: Outlook web 링크
    """

    message_id: str
    subject: str
    from_address: str
    received_date: str
    body_text: str
    summary_text: str = ""
    web_link: str = ""


class MailSearchService:
    """
    SQLite 메일 DB 기반 하이브리드 검색(키워드 + 벡터 유사도) 서비스.
    """

    def __init__(self, db_path: Path) -> None:
        """
        메일 검색 서비스 인스턴스를 초기화한다.

        Args:
            db_path: SQLite DB 경로
        """
        self._db_path = db_path
        self._has_web_link_column_cache: bool | None = None
        self._has_summary_column_cache: bool | None = None
        self._preferred_outlook_link_column_cache: str | None = None
        self._table_columns_cache: set[str] | None = None

    def search(
        self,
        query: str,
        person: str = "",
        start_date: str = "",
        end_date: str = "",
        limit: int = 5,
    ) -> dict[str, object]:
        """
        메일 조건 검색을 수행한다.

        Args:
            query: 사용자 질의
            person: 사람명 필터
            start_date: 시작일(YYYY-MM-DD)
            end_date: 종료일(YYYY-MM-DD)
            limit: 반환 개수

        Returns:
            검색 결과 payload
        """
        normalized_query = str(query or "").strip()
        normalized_person = str(person or "").strip()
        target_limit = normalize_limit(limit=limit)
        candidate_limit = self._resolve_candidate_limit(
            target_limit=target_limit,
            person=normalized_person,
            start_date=start_date,
            end_date=end_date,
            query=normalized_query,
        )
        started_at = time.perf_counter()
        rows = self._fetch_candidates(
            query=normalized_query,
            person=normalized_person,
            start_date=start_date,
            end_date=end_date,
            candidate_limit=candidate_limit,
        )
        if not rows:
            return {
                "action": "mail_search",
                "status": "completed",
                "results": [],
                "count": 0,
                "aggregated_summary": [],
                "metrics": {"candidate_count": 0, "elapsed_ms": elapsed_ms(started_at)},
            }
        reranked = rerank_candidates(query=normalized_query, rows=rows)
        filtered = self._filter_low_relevance_rows(query=normalized_query, rows=reranked)
        results = [to_result_payload(row=item) for item in filtered[:target_limit]]
        aggregated_summary = build_aggregated_summary(results=results, line_target=min(5, target_limit))
        return {
            "action": "mail_search",
            "status": "completed",
            "results": results,
            "count": len(results),
            "aggregated_summary": aggregated_summary,
            "query": normalized_query,
            "person": normalized_person,
            "start_date": str(start_date or "").strip(),
            "end_date": str(end_date or "").strip(),
            "metrics": {
                "candidate_count": len(rows),
                "reranked_count": len(reranked),
                "filtered_count": len(filtered),
                "returned_count": len(results),
                "elapsed_ms": elapsed_ms(started_at),
            },
        }

    def _filter_low_relevance_rows(self, query: str, rows: list[MailSearchResult]) -> list[MailSearchResult]:
        """
        재랭킹 결과에서 질의 핵심 키워드 매칭이 낮은 항목을 제거한다.

        Args:
            query: 사용자 질의
            rows: 재랭킹된 후보 목록

        Returns:
            핵심 키워드 최소 매칭을 통과한 목록
        """
        if not rows:
            return []
        person_anchors = extract_person_anchor_tokens(query=query)
        person_filtered = [row for row in rows if row_matches_person_anchors(row=row, anchors=person_anchors)]
        if person_anchors and not person_filtered:
            logger.info(
                "mail_search 인물 앵커 필터 0건 처리: query=%s anchors=%s",
                query[:80],
                ",".join(person_anchors),
            )
            return []
        scoped_person_rows = person_filtered if person_anchors else rows
        required_body_phrases = extract_required_body_phrases(query=query)
        strict_filtered = [
            row for row in scoped_person_rows if has_required_body_phrases(row=row, phrases=required_body_phrases)
        ]
        if required_body_phrases and not strict_filtered:
            logger.info(
                "mail_search strict body filter 적용: query=%s required_phrases=%s matched=0",
                query[:80],
                ",".join(required_body_phrases[:6]),
            )
            return []
        scoped_rows = strict_filtered if required_body_phrases else rows
        keywords = extract_meaningful_query_tokens(text=query)
        min_hits = min_keyword_hits_for_query(query=query)
        if min_hits <= 0:
            return scoped_rows
        filtered = [row for row in scoped_rows if keyword_match_count(row=row, keywords=keywords) >= min_hits]
        if filtered:
            if _should_reject_top_result_for_high_specific_query(
                query_keywords=keywords,
                top_row=filtered[0],
            ):
                logger.info(
                    "mail_search 고특이도 하드게이트 적용: query=%s top_subject=%s",
                    query[:80],
                    str(filtered[0].subject or "")[:80],
                )
                return []
            return filtered
        if required_body_phrases:
            return []
        if len(keywords) >= 5:
            logger.info(
                "mail_search 고특이도 질의 0건 처리: query=%s keywords=%s",
                query[:80],
                ",".join(keywords[:8]),
            )
            return []
        logger.info(
            "mail_search 키워드 필터 미적용 fallback: query=%s keywords=%s min_hits=%s",
            query[:80],
            ",".join(keywords[:6]),
            min_hits,
        )
        return scoped_rows

    def _fetch_candidates(
        self,
        query: str,
        person: str,
        start_date: str,
        end_date: str,
        candidate_limit: int,
    ) -> list[MailSearchResult]:
        """
        DB에서 검색 후보 메일 목록을 조회한다.

        Args:
            query: 사용자 질의
            person: 사람명 필터
            start_date: 시작일
            end_date: 종료일
            candidate_limit: 후보 조회 상한

        Returns:
            후보 메일 목록
        """
        if not self._db_path.exists():
            logger.warning("메일 검색 DB 파일이 없습니다: %s", self._db_path)
            return []
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            sql, params = self._build_candidate_query(
                query=query,
                person=person,
                start_date=start_date,
                end_date=end_date,
                candidate_limit=candidate_limit,
            )
            rows = conn.execute(sql, params).fetchall()
        finally:
            conn.close()
        return [_row_to_result(row=row) for row in rows]

    def _build_candidate_query(
        self,
        query: str,
        person: str,
        start_date: str,
        end_date: str,
        candidate_limit: int,
    ) -> tuple[str, tuple[object, ...]]:
        """
        검색 조건 기반 SQL과 파라미터를 생성한다.

        Args:
            query: 사용자 질의
            person: 사람명 필터
            start_date: 시작일
            end_date: 종료일
            candidate_limit: 후보 조회 상한

        Returns:
            (SQL, 파라미터) 튜플
        """
        conditions: list[str] = []
        params: list[object] = []
        query_tokens = self._build_candidate_query_tokens(query=query)
        if query_tokens:
            token_conditions = []
            for token in query_tokens:
                token_conditions.append(
                    "(subject LIKE ? OR from_address LIKE ? OR COALESCE(body_clean, body_full, body_preview, '') LIKE ?)"
                )
                like_token = f"%{token}%"
                params.extend([like_token, like_token, like_token])
            conditions.append("(" + " OR ".join(token_conditions) + ")")
        if person:
            person_like = f"%{person}%"
            conditions.append("(from_address LIKE ? OR COALESCE(body_clean, body_full, body_preview, '') LIKE ?)")
            params.extend([person_like, person_like])
        if start_date:
            conditions.append("received_date >= ?")
            params.append(str(start_date).strip())
        if end_date:
            conditions.append("received_date <= ?")
            params.append(str(end_date).strip())
        where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        web_link_clause = self._build_link_select_clause()
        summary_clause = "COALESCE(summary, '') AS summary_text " if self._has_summary_column() else "'' AS summary_text "
        sql = (
            "SELECT message_id, subject, from_address, received_date, "
            "COALESCE(body_clean, body_full, body_preview, '') AS body_text, "
            f"{web_link_clause}"
            f"{summary_clause}"
            "FROM emails "
            f"{where_clause} "
            "ORDER BY received_date DESC "
            "LIMIT ?"
        )
        params.append(candidate_limit)
        return sql, tuple(params)

    def _resolve_candidate_limit(
        self,
        target_limit: int,
        person: str,
        start_date: str,
        end_date: str,
        query: str,
    ) -> int:
        """
        검색 조건에 따라 후보 조회 상한을 동적으로 계산한다.

        Args:
            target_limit: 최종 반환 목표 개수
            person: 사람명 필터
            start_date: 시작일 필터
            end_date: 종료일 필터
            query: 사용자 질의

        Returns:
            후보 조회 상한
        """
        has_person_filter = bool(str(person or "").strip())
        has_date_filter = bool(str(start_date or "").strip() or str(end_date or "").strip())
        meaningful_tokens = extract_meaningful_query_tokens(text=query)
        if has_person_filter and has_date_filter:
            return max(12, target_limit * 3)
        if has_person_filter or has_date_filter:
            return max(16, target_limit * 4)
        if len(meaningful_tokens) >= 4:
            return max(20, target_limit * 5)
        return max(30, target_limit * 8)

    def _build_candidate_query_tokens(self, query: str) -> list[str]:
        """
        SQL 후보 조회에 사용할 토큰 목록을 생성한다.

        Args:
            query: 사용자 질의

        Returns:
            토큰 목록(최대 4개)
        """
        meaningful_tokens = extract_meaningful_query_tokens(text=query)
        if meaningful_tokens:
            return meaningful_tokens[:4]
        fallback_tokens = tokenize_for_search(text=query)
        return fallback_tokens[:2]

    def _has_web_link_column(self) -> bool:
        """
        emails 테이블의 web_link 컬럼 존재 여부를 반환한다.

        Returns:
            web_link 컬럼 존재 여부
        """
        cached = self._has_web_link_column_cache
        if cached is not None:
            return cached
        has_column = "web_link" in self._get_table_columns()
        self._has_web_link_column_cache = has_column
        return has_column

    def _has_summary_column(self) -> bool:
        """
        emails 테이블의 summary 컬럼 존재 여부를 반환한다.

        Returns:
            summary 컬럼 존재 여부
        """
        cached = self._has_summary_column_cache
        if cached is not None:
            return cached
        has_column = "summary" in self._get_table_columns()
        self._has_summary_column_cache = has_column
        return has_column

    def _build_link_select_clause(self) -> str:
        """
        링크 컬럼 우선순위 정책에 맞는 SELECT 절을 생성한다.

        Returns:
            `AS web_link`가 포함된 SELECT 절 문자열
        """
        preferred_column = self._resolve_preferred_outlook_link_column()
        if preferred_column:
            return f"COALESCE({preferred_column}, web_link, '') AS web_link, "
        if self._has_web_link_column():
            return "COALESCE(web_link, '') AS web_link, "
        return "'' AS web_link, "

    def _resolve_preferred_outlook_link_column(self) -> str:
        """
        Outlook 전용 링크 컬럼명을 우선순위에 따라 해석한다.

        Returns:
            선택된 컬럼명. 없으면 빈 문자열
        """
        cached = self._preferred_outlook_link_column_cache
        if cached is not None:
            return cached
        columns = self._get_table_columns()
        selected = next((column for column in PREFERRED_OUTLOOK_LINK_COLUMNS if column in columns), "")
        self._preferred_outlook_link_column_cache = selected
        return selected

    def _get_table_columns(self) -> set[str]:
        """
        `emails` 테이블 컬럼 집합을 캐시 기반으로 반환한다.

        Returns:
            소문자 컬럼명 집합
        """
        cached = self._table_columns_cache
        if cached is not None:
            return cached
        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute("PRAGMA table_info(emails)").fetchall()
            columns = {str(row[1]).strip().lower() for row in rows if len(row) > 1}
            self._table_columns_cache = columns
            return columns
        finally:
            conn.close()


def _row_to_result(row: sqlite3.Row) -> MailSearchResult:
    """
    sqlite row를 MailSearchResult로 변환한다.

    Args:
        row: sqlite 조회 row

    Returns:
        표준 검색 결과 모델
    """
    return MailSearchResult(
        message_id=str(row["message_id"] or ""),
        subject=str(row["subject"] or ""),
        from_address=str(row["from_address"] or ""),
        received_date=str(row["received_date"] or ""),
        body_text=str(row["body_text"] or ""),
        summary_text=str(row["summary_text"] or ""),
        web_link=str(row["web_link"] or ""),
    )


def _should_reject_top_result_for_high_specific_query(
    query_keywords: list[str],
    top_row: MailSearchResult,
) -> bool:
    """
    고특이도 질의에서 상위 1건의 키워드 일치가 낮으면 결과를 거부한다.

    Args:
        query_keywords: 질의 핵심 키워드 목록
        top_row: 필터링 이후 상위 메일

    Returns:
        거부 조건이면 True
    """
    keyword_count = len(query_keywords)
    if keyword_count < 5:
        return False
    top_hits = keyword_match_count(row=top_row, keywords=query_keywords)
    required_hits = 4 if keyword_count >= 6 else 3
    if top_hits >= required_hits:
        return False
    if _has_identifier_anchor_match(query_keywords=query_keywords, top_row=top_row):
        return False
    return True


def _has_identifier_anchor_match(query_keywords: list[str], top_row: MailSearchResult) -> bool:
    """
    질의 내 식별자 성격 토큰(영문/숫자 포함)이 상위 메일에 존재하는지 확인한다.

    Args:
        query_keywords: 질의 핵심 키워드 목록
        top_row: 필터링 이후 상위 메일

    Returns:
        식별자 토큰이 제목/요약/본문에 포함되면 True
    """
    anchor_tokens = [token for token in query_keywords if _is_identifier_token(token)]
    if not anchor_tokens:
        return False
    haystack = " ".join(
        [
            str(top_row.subject or ""),
            str(top_row.summary_text or ""),
            str(top_row.body_text or ""),
        ]
    ).lower()
    return any(token in haystack for token in anchor_tokens)


def _is_identifier_token(token: str) -> bool:
    """
    식별자 성격 토큰(영문/숫자 포함)인지 판별한다.

    Args:
        token: 질의 토큰

    Returns:
        식별자 성격 토큰이면 True
    """
    normalized = str(token or "").strip().lower()
    if len(normalized) < 2:
        return False
    return bool(re.search(r"[a-z0-9]", normalized))
