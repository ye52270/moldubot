from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from app.core.logging_config import get_logger

logger = get_logger(__name__)
QUEUE_STATUS_PENDING = "pending"
QUEUE_STATUS_PROCESSING = "processing"
QUEUE_STATUS_COMPLETED = "completed"
QUEUE_STATUS_FAILED = "failed"
DEFAULT_MAX_RETRIES = 3


@dataclass
class MailSummaryQueueJob:
    """
    summary queue 작업 단건 데이터 구조.

    Attributes:
        job_id: queue row 식별자
        message_id: 대상 메일 message_id
        status: 작업 상태
        attempt_count: 시도 횟수
    """

    job_id: int
    message_id: str
    status: str
    attempt_count: int


@dataclass
class MailSummaryQueueBackfillResult:
    """
    summary queue 백필 enqueue 결과.

    Attributes:
        scanned: 조회한 메일 건수
        enqueued: 신규 enqueue 건수
        skipped_existing: 기존 queue 존재로 스킵 건수
    """

    scanned: int
    enqueued: int
    skipped_existing: int


class MailSummaryQueueService:
    """
    메일 summary 생성 큐를 SQLite 테이블로 관리하는 서비스.
    """

    def __init__(self, db_path: Path) -> None:
        """
        큐 서비스 인스턴스를 초기화한다.

        Args:
            db_path: SQLite DB 파일 경로
        """
        self._db_path = db_path

    def enqueue_message(self, message_id: str, requested_by: str = "upsert", force_requeue: bool = False) -> bool:
        """
        message_id를 summary queue에 적재한다.

        Args:
            message_id: 대상 메일 식별자
            requested_by: 적재 트리거 구분자
            force_requeue: True면 기존 작업이 있어도 `pending`으로 재큐잉

        Returns:
            신규 enqueue 성공 시 True, 중복이면 False
        """
        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id or not self._db_path.exists():
            return False
        with sqlite3.connect(str(self._db_path)) as conn:
            self._ensure_queue_table(conn=conn)
            cursor = conn.execute(
                "INSERT OR IGNORE INTO mail_summary_queue (message_id, status, requested_by) VALUES (?, ?, ?)",
                (normalized_message_id, QUEUE_STATUS_PENDING, str(requested_by or "upsert").strip()),
            )
            if cursor.rowcount == 0 and force_requeue:
                cursor = conn.execute(
                    "UPDATE mail_summary_queue SET status = ?, last_error = '', updated_at = CURRENT_TIMESTAMP "
                    "WHERE message_id = ?",
                    (QUEUE_STATUS_PENDING, normalized_message_id),
                )
            conn.commit()
            return cursor.rowcount > 0

    def enqueue_backfill(self, limit: int = 0, include_existing: bool = False) -> MailSummaryQueueBackfillResult:
        """
        emails 테이블을 스캔해 summary queue 백필 enqueue를 수행한다.

        Args:
            limit: 최대 스캔 건수(0 이하면 전체)
            include_existing: True면 summary가 이미 있어도 enqueue

        Returns:
            enqueue 집계 결과
        """
        if not self._db_path.exists():
            return MailSummaryQueueBackfillResult(scanned=0, enqueued=0, skipped_existing=0)
        target_limit = max(0, int(limit))
        scanned = 0
        enqueued = 0
        skipped_existing = 0
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_queue_table(conn=conn)
            where_clause = "" if include_existing else "WHERE COALESCE(summary, '') = ''"
            limit_clause = f" LIMIT {target_limit}" if target_limit else ""
            rows = conn.execute(
                "SELECT message_id FROM emails "
                f"{where_clause} "
                "ORDER BY received_date DESC"
                f"{limit_clause}"
            ).fetchall()
            for row in rows:
                scanned += 1
                message_id = str(row["message_id"] or "").strip()
                if not message_id:
                    continue
                cursor = conn.execute(
                    "INSERT OR IGNORE INTO mail_summary_queue (message_id, status, requested_by) VALUES (?, ?, ?)",
                    (message_id, QUEUE_STATUS_PENDING, "backfill"),
                )
                if cursor.rowcount == 0 and include_existing:
                    cursor = conn.execute(
                        "UPDATE mail_summary_queue SET status = ?, last_error = '', updated_at = CURRENT_TIMESTAMP "
                        "WHERE message_id = ?",
                        (QUEUE_STATUS_PENDING, message_id),
                    )
                if cursor.rowcount > 0:
                    enqueued += 1
                else:
                    skipped_existing += 1
            conn.commit()
        return MailSummaryQueueBackfillResult(scanned=scanned, enqueued=enqueued, skipped_existing=skipped_existing)

    def claim_next_job(self) -> MailSummaryQueueJob | None:
        """
        처리 가능한 다음 pending 작업을 claim한다.

        Returns:
            claim 성공 시 작업 정보, 없으면 None
        """
        if not self._db_path.exists():
            return None
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            self._ensure_queue_table(conn=conn)
            row = conn.execute(
                "SELECT id, message_id, status, attempt_count FROM mail_summary_queue "
                "WHERE status IN (?, ?) "
                "ORDER BY updated_at ASC, id ASC LIMIT 1",
                (QUEUE_STATUS_PENDING, QUEUE_STATUS_FAILED),
            ).fetchone()
            if row is None:
                return None
            job_id = int(row["id"])
            current_attempt = int(row["attempt_count"] or 0)
            conn.execute(
                "UPDATE mail_summary_queue SET status = ?, attempt_count = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (QUEUE_STATUS_PROCESSING, current_attempt + 1, job_id),
            )
            conn.commit()
            return MailSummaryQueueJob(
                job_id=job_id,
                message_id=str(row["message_id"] or "").strip(),
                status=QUEUE_STATUS_PROCESSING,
                attempt_count=current_attempt + 1,
            )

    def load_mail_payload(self, message_id: str) -> dict[str, str] | None:
        """
        summary 생성을 위한 메일 본문/제목 payload를 조회한다.

        Args:
            message_id: 대상 메일 식별자

        Returns:
            payload 사전 또는 None
        """
        if not self._db_path.exists():
            return None
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT message_id, COALESCE(subject, '') AS subject, COALESCE(from_address, '') AS from_address, "
                "COALESCE(received_date, '') AS received_date, "
                "COALESCE(body_clean, body_full, body_preview, '') AS body_text "
                "FROM emails WHERE message_id = ? LIMIT 1",
                (str(message_id or "").strip(),),
            ).fetchone()
        if row is None:
            return None
        return {
            "message_id": str(row["message_id"] or "").strip(),
            "subject": str(row["subject"] or "").strip(),
            "from_address": str(row["from_address"] or "").strip(),
            "received_date": str(row["received_date"] or "").strip(),
            "body_text": str(row["body_text"] or "").strip(),
        }

    def mark_completed(self, job_id: int, message_id: str, summary: str, category: str) -> None:
        """
        작업 완료 처리와 함께 emails.summary/category를 갱신한다.

        Args:
            job_id: queue 작업 ID
            message_id: 대상 message_id
            summary: 생성된 요약
            category: 분류 카테고리
        """
        if not self._db_path.exists():
            return
        with sqlite3.connect(str(self._db_path)) as conn:
            self._ensure_queue_table(conn=conn)
            summary_value = str(summary or "").strip()
            category_value = str(category or "").strip()
            if self._has_category_column(conn=conn):
                conn.execute(
                    "UPDATE emails SET summary = ?, category = ? WHERE message_id = ?",
                    (summary_value, category_value, str(message_id or "").strip()),
                )
            else:
                conn.execute(
                    "UPDATE emails SET summary = ? WHERE message_id = ?",
                    (summary_value, str(message_id or "").strip()),
                )
            conn.execute(
                "UPDATE mail_summary_queue SET status = ?, last_error = '', updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (QUEUE_STATUS_COMPLETED, int(job_id)),
            )
            conn.commit()

    def mark_failed(self, job_id: int, error_message: str, max_retries: int = DEFAULT_MAX_RETRIES) -> None:
        """
        작업 실패 상태를 기록하고 재시도 한도를 초과하면 failed 상태로 남긴다.

        Args:
            job_id: queue 작업 ID
            error_message: 실패 메시지
            max_retries: 최대 재시도 횟수
        """
        if not self._db_path.exists():
            return
        with sqlite3.connect(str(self._db_path)) as conn:
            conn.row_factory = sqlite3.Row
            row = conn.execute(
                "SELECT attempt_count FROM mail_summary_queue WHERE id = ? LIMIT 1",
                (int(job_id),),
            ).fetchone()
            attempt_count = int(row["attempt_count"] or 0) if row is not None else 0
            status = QUEUE_STATUS_FAILED if attempt_count >= max(1, int(max_retries)) else QUEUE_STATUS_PENDING
            conn.execute(
                "UPDATE mail_summary_queue SET status = ?, last_error = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                (status, str(error_message or "").strip()[:1000], int(job_id)),
            )
            conn.commit()

    def _ensure_queue_table(self, conn: sqlite3.Connection) -> None:
        """
        mail_summary_queue 테이블을 생성한다(없으면).

        Args:
            conn: SQLite 연결 객체
        """
        conn.execute(
            "CREATE TABLE IF NOT EXISTS mail_summary_queue ("
            "id INTEGER PRIMARY KEY AUTOINCREMENT, "
            "message_id TEXT UNIQUE NOT NULL, "
            "status TEXT NOT NULL DEFAULT 'pending', "
            "attempt_count INTEGER NOT NULL DEFAULT 0, "
            "last_error TEXT NOT NULL DEFAULT '', "
            "requested_by TEXT NOT NULL DEFAULT 'upsert', "
            "created_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP, "
            "updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP)"
        )

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
