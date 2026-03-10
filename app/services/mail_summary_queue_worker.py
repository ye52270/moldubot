from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from app.core.logging_config import get_logger
from app.services.mail_summary_llm_service import MailSummaryLLMService
from app.services.mail_summary_queue_service import MailSummaryQueueService
from app.services.mail_vector_index_service import MailVectorIndexService

logger = get_logger(__name__)


@dataclass
class MailSummaryWorkerRunResult:
    """
    summary worker 실행 집계 결과.

    Attributes:
        processed: 처리 완료 건수
        failed: 실패 건수
        empty: 큐가 비어 종료된 횟수
    """

    processed: int
    failed: int
    empty: int


class MailSummaryQueueWorker:
    """
    summary queue를 순차 처리하는 worker.
    """

    def __init__(self, db_path: Path) -> None:
        """
        worker 인스턴스를 초기화한다.

        Args:
            db_path: SQLite DB 파일 경로
        """
        self._queue_service = MailSummaryQueueService(db_path=db_path)
        self._llm_service = MailSummaryLLMService()
        self._vector_index_service = MailVectorIndexService()

    def process_once(self) -> bool:
        """
        큐 작업 1건을 처리한다.

        Returns:
            처리 수행 시 True, 큐가 비어 있으면 False
        """
        job = self._queue_service.claim_next_job()
        if job is None:
            return False
        payload = self._queue_service.load_mail_payload(message_id=job.message_id)
        if payload is None:
            self._queue_service.mark_failed(job_id=job.job_id, error_message="mail_payload_not_found")
            return True
        try:
            result = self._llm_service.summarize(
                subject=str(payload.get("subject") or ""),
                body_text=str(payload.get("body_text") or ""),
            )
            self._vector_index_service.upsert_mail_document(
                message_id=job.message_id,
                subject=str(payload.get("subject") or ""),
                body_text=str(payload.get("body_text") or ""),
                summary=result.summary,
                category=result.category,
                from_address=str(payload.get("from_address") or ""),
                received_date=str(payload.get("received_date") or ""),
            )
            self._queue_service.mark_completed(
                job_id=job.job_id,
                message_id=job.message_id,
                summary=result.summary,
                category=result.category,
            )
            logger.info(
                "mail_summary_worker_completed: message_id=%s source=%s category=%s",
                job.message_id,
                result.source,
                result.category,
            )
        except Exception as exc:  # noqa: BLE001
            self._queue_service.mark_failed(job_id=job.job_id, error_message=str(exc))
            logger.error("mail_summary_worker_failed: message_id=%s error=%s", job.message_id, exc)
        return True

    def process_many(self, max_jobs: int = 50) -> MailSummaryWorkerRunResult:
        """
        큐 작업을 최대 `max_jobs`건 처리한다.

        Args:
            max_jobs: 최대 처리 건수

        Returns:
            실행 집계 결과
        """
        processed = 0
        failed = 0
        empty = 0
        for _ in range(max(1, int(max_jobs))):
            handled = self.process_once()
            if not handled:
                empty += 1
                break
            processed += 1
        return MailSummaryWorkerRunResult(processed=processed, failed=failed, empty=empty)
