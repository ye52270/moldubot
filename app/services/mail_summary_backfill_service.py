from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.core.logging_config import get_logger
from app.services.mail_text_utils import select_salient_summary_sentences

logger = get_logger(__name__)
DEFAULT_SUMMARY_LINE_TARGET = 3
DEFAULT_BATCH_SIZE = 200
CATEGORY_GENERAL = "일반"
CATEGORY_URGENT = "긴급"
CATEGORY_REPLY_REQUIRED = "회신필요"
URGENT_TOKENS = (
    "긴급",
    "asap",
    "즉시",
    "오늘중",
    "장애",
    "중단",
    "차단",
    "실패",
    "오류",
    "critical",
    "sev",
    "p1",
    "마감",
    "deadline",
    "지연",
    "이슈",
)
REPLY_REQUIRED_TOKENS = (
    "회신",
    "답변",
    "답장",
    "회답",
    "답변 부탁",
    "회신 부탁",
    "회신요청",
    "확인 부탁",
    "검토 부탁",
    "검토 요청",
    "요청드립니다",
    "문의",
    "피드백",
)


@dataclass
class SummaryBackfillResult:
    """
    summary 백필 실행 결과를 담는 데이터 구조.

    Attributes:
        scanned: 조회한 레코드 수
        updated: 실제 update 반영 건수
        skipped_existing: 기존 summary가 있어 건너뛴 건수
        skipped_empty_body: 본문 기반 요약 생성이 불가해 건너뛴 건수
        category_updated: category 반영 건수
        dry_run: 드라이런 여부
    """

    scanned: int
    updated: int
    category_updated: int
    skipped_existing: int
    skipped_empty_body: int
    dry_run: bool


class MailSummaryBackfillService:
    """
    `emails.summary` 누락 데이터를 본문 기반으로 채우는 백필 서비스.
    """

    def __init__(self, db_path: Path) -> None:
        """
        백필 서비스 인스턴스를 초기화한다.

        Args:
            db_path: SQLite DB 파일 경로
        """
        self._db_path = db_path

    def backfill(
        self,
        limit: int = 0,
        batch_size: int = DEFAULT_BATCH_SIZE,
        dry_run: bool = False,
        only_missing: bool = True,
        include_category: bool = True,
    ) -> SummaryBackfillResult:
        """
        summary 백필을 실행한다.

        Args:
            limit: 최대 처리 건수(0 이하면 전체)
            batch_size: 배치 조회 크기
            dry_run: True면 DB 변경 없이 대상만 계산
            only_missing: True면 summary/category가 비어 있는 레코드만 처리
            include_category: True면 category 컬럼이 있을 때 자동 분류를 함께 반영

        Returns:
            백필 실행 결과
        """
        if not self._db_path.exists():
            logger.warning("summary 백필 중단: DB 파일이 없습니다: %s", self._db_path)
            return SummaryBackfillResult(0, 0, 0, 0, 0, dry_run)
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            if not self._has_summary_column(conn=conn):
                logger.warning("summary 백필 중단: emails.summary 컬럼이 없습니다.")
                return SummaryBackfillResult(0, 0, 0, 0, 0, dry_run)
            has_category_column = self._has_category_column(conn=conn)
            return self._execute_backfill(
                conn=conn,
                limit=limit,
                batch_size=batch_size,
                dry_run=dry_run,
                only_missing=only_missing,
                include_category=include_category and has_category_column,
            )

    def _execute_backfill(
        self,
        conn: sqlite3.Connection,
        limit: int,
        batch_size: int,
        dry_run: bool,
        only_missing: bool,
        include_category: bool,
    ) -> SummaryBackfillResult:
        """
        백필 대상 조회/요약 생성/업데이트를 수행한다.

        Args:
            conn: SQLite 연결 객체
            limit: 최대 처리 건수
            batch_size: 배치 조회 크기
            dry_run: 드라이런 여부
            only_missing: 누락 summary만 처리 여부
            include_category: category 컬럼 반영 여부

        Returns:
            백필 실행 결과
        """
        scanned = 0
        updated = 0
        category_updated = 0
        skipped_existing = 0
        skipped_empty_body = 0
        offset = 0
        target_limit = max(0, int(limit))
        fetch_size = max(1, int(batch_size))
        while True:
            remaining = max(0, target_limit - scanned) if target_limit else fetch_size
            rows = self._fetch_rows(conn=conn, offset=offset, size=min(fetch_size, remaining or fetch_size))
            if not rows:
                break
            offset += len(rows)
            scanned += len(rows)
            for row in rows:
                row_result = self._process_row(
                    conn=conn,
                    row=row,
                    dry_run=dry_run,
                    only_missing=only_missing,
                    include_category=include_category,
                )
                updated += 1 if row_result.summary_updated else 0
                category_updated += 1 if row_result.category_updated else 0
                skipped_existing += 1 if row_result.skipped_existing else 0
                skipped_empty_body += 1 if row_result.skipped_empty_body else 0
            if target_limit and scanned >= target_limit:
                break
        if not dry_run:
            conn.commit()
        return SummaryBackfillResult(
            scanned=scanned,
            updated=updated,
            category_updated=category_updated,
            skipped_existing=skipped_existing,
            skipped_empty_body=skipped_empty_body,
            dry_run=dry_run,
        )

    def _fetch_rows(self, conn: sqlite3.Connection, offset: int, size: int) -> list[sqlite3.Row]:
        """
        백필 대상 후보 레코드를 조회한다.

        Args:
            conn: SQLite 연결 객체
            offset: 조회 시작 오프셋
            size: 조회 건수

        Returns:
            메일 row 목록
        """
        query = (
            "SELECT message_id, COALESCE(subject, '') AS subject_text, COALESCE(from_address, '') AS from_address, "
            "COALESCE(body_clean, '') AS body_clean, COALESCE(body_full, '') AS body_full, COALESCE(body_preview, '') AS body_preview, "
            "COALESCE(summary, '') AS summary_text, COALESCE(category, '') AS category_text "
            "FROM emails ORDER BY received_date DESC LIMIT ? OFFSET ?"
        )
        return list(conn.execute(query, (size, offset)).fetchall())

    def _process_row(
        self,
        conn: sqlite3.Connection,
        row: sqlite3.Row,
        dry_run: bool,
        only_missing: bool,
        include_category: bool,
    ) -> "RowBackfillResult":
        """
        단건 row에 대해 summary 생성/저장을 수행한다.

        Args:
            conn: SQLite 연결 객체
            row: 대상 메일 row
            dry_run: 드라이런 여부
            only_missing: 누락 summary만 처리 여부
            include_category: category 컬럼 반영 여부

        Returns:
            단건 처리 결과
        """
        current_summary = str(row["summary_text"] or "").strip()
        current_category = str(row["category_text"] or "").strip()
        need_summary_update = not current_summary if only_missing else True
        summary = self._build_summary_text(
            body_clean=str(row["body_clean"] or ""),
            body_full=str(row["body_full"] or ""),
            body_preview=str(row["body_preview"] or ""),
            subject_text=str(row["subject_text"] or ""),
        )
        has_summary_update = need_summary_update and bool(summary)
        has_category_update = include_category and (not current_category if only_missing else True)
        category_value = self._classify_category(
            subject_text=str(row["subject_text"] or ""),
            body_text="\n".join(
                [
                    str(row["body_clean"] or ""),
                    str(row["body_full"] or ""),
                    str(row["body_preview"] or ""),
                    current_summary or summary,
                ]
            ),
        )
        if has_category_update and not category_value:
            has_category_update = False
        if not has_summary_update and not has_category_update:
            if need_summary_update and not summary:
                return RowBackfillResult(
                    summary_updated=False,
                    category_updated=False,
                    skipped_existing=False,
                    skipped_empty_body=True,
                )
            return RowBackfillResult(
                summary_updated=False,
                category_updated=False,
                skipped_existing=True,
                skipped_empty_body=False,
            )
        if not dry_run:
            if has_summary_update and has_category_update:
                conn.execute(
                    "UPDATE emails SET summary = ?, category = ? WHERE message_id = ?",
                    (summary, category_value, str(row["message_id"] or "").strip()),
                )
            elif has_summary_update:
                conn.execute(
                    "UPDATE emails SET summary = ? WHERE message_id = ?",
                    (summary, str(row["message_id"] or "").strip()),
                )
            else:
                conn.execute(
                    "UPDATE emails SET category = ? WHERE message_id = ?",
                    (category_value, str(row["message_id"] or "").strip()),
                )
        return RowBackfillResult(
            summary_updated=has_summary_update,
            category_updated=has_category_update,
            skipped_existing=False,
            skipped_empty_body=False,
        )

    def _build_summary_text(
        self,
        body_clean: str,
        body_full: str,
        body_preview: str,
        subject_text: str,
    ) -> str:
        """
        본문 텍스트에서 저장용 summary를 생성한다.

        Args:
            body_clean: 정제 본문
            body_full: 원문 본문
            body_preview: 본문 미리보기
            subject_text: 메일 제목

        Returns:
            단일 라인 summary 문자열
        """
        candidates = (body_clean, body_full, body_preview)
        for candidate in candidates:
            lines = select_salient_summary_sentences(
                text=str(candidate or ""),
                line_target=DEFAULT_SUMMARY_LINE_TARGET,
            )
            normalized = [line.strip() for line in lines if str(line or "").strip()]
            summary = " ".join(normalized).strip()
            if summary:
                return summary
        fallback = str(subject_text or "").strip()
        if fallback:
            return f"제목 기준 요약: {fallback}"
        return ""

    def _classify_category(self, subject_text: str, body_text: str) -> str:
        """
        메일 문맥을 기준으로 category를 분류한다.

        Args:
            subject_text: 메일 제목
            body_text: 메일 본문/요약 통합 텍스트

        Returns:
            분류된 category 문자열
        """
        normalized = f"{str(subject_text or '')}\n{str(body_text or '')}".lower()
        urgent_score = sum(1 for token in URGENT_TOKENS if token in normalized)
        reply_score = sum(1 for token in REPLY_REQUIRED_TOKENS if token in normalized)
        if urgent_score >= 1:
            return CATEGORY_URGENT
        if reply_score >= 1:
            return CATEGORY_REPLY_REQUIRED
        return CATEGORY_GENERAL

    def _has_summary_column(self, conn: sqlite3.Connection) -> bool:
        """
        emails 테이블의 summary 컬럼 존재 여부를 확인한다.

        Args:
            conn: SQLite 연결 객체

        Returns:
            summary 컬럼 존재 여부
        """
        rows = conn.execute("PRAGMA table_info(emails)").fetchall()
        return any(str(row[1]).lower() == "summary" for row in rows)

    def _has_category_column(self, conn: sqlite3.Connection) -> bool:
        """
        emails 테이블의 category 컬럼 존재 여부를 확인한다.

        Args:
            conn: SQLite 연결 객체

        Returns:
            category 컬럼 존재 여부
        """
        rows = conn.execute("PRAGMA table_info(emails)").fetchall()
        return any(str(row[1]).lower() == "category" for row in rows)


@dataclass
class RowBackfillResult:
    """
    단건 백필 처리 결과를 담는 데이터 구조.

    Attributes:
        summary_updated: summary 업데이트 반영 여부
        category_updated: category 업데이트 반영 여부
        skipped_existing: 기존값 보존으로 스킵 여부
        skipped_empty_body: 요약 생성 불가 스킵 여부
    """

    summary_updated: bool
    category_updated: bool
    skipped_existing: bool
    skipped_empty_body: bool
