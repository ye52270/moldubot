from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass
from pathlib import Path

from app.core.logging_config import get_logger
from app.integrations.microsoft_graph.mail_client import GraphMailClient, GraphMailMessage
from app.services.mail_service import MailRecord, MailService

logger = get_logger(__name__)


@dataclass(frozen=True)
class MailSyncResult:
    """
    Graph 최근 메일 pull sync 집계 결과.
    """

    fetched: int
    inserted: int
    updated: int
    skipped_older: int

    def as_dict(self) -> dict[str, int]:
        """
        결과를 직렬화 가능한 사전으로 변환한다.

        Returns:
            결과 사전
        """
        return asdict(self)


class MailSyncService:
    """
    Graph 최근 메일을 로컬 DB와 summary queue에 동기화한다.
    """

    def __init__(self, db_path: Path, graph_client: GraphMailClient | None = None) -> None:
        """
        동기화 서비스 인스턴스를 초기화한다.

        Args:
            db_path: 로컬 SQLite 경로
            graph_client: Graph 메일 클라이언트
        """
        self._db_path = db_path
        self._mail_service = MailService(db_path=db_path)
        self._graph_client = graph_client or GraphMailClient()

    def sync_recent_messages(self, limit: int = 20) -> MailSyncResult:
        """
        최근 메일을 Graph에서 가져와 로컬 DB에 동기화한다.

        Args:
            limit: Graph 조회 최대 건수

        Returns:
            동기화 집계 결과
        """
        latest_received_date = self._load_latest_received_date()
        fetched = inserted = updated = skipped_older = 0
        for message in self._graph_client.list_recent_messages(limit=limit):
            fetched += 1
            if self._should_skip_older_message(message=message, latest_received_date=latest_received_date):
                skipped_older += 1
                continue
            existed = self._mail_service.read_mail_by_message_id(message.message_id) is not None
            self._mail_service.upsert_mail_record(mail=self._build_mail_record(message=message))
            if existed:
                updated += 1
            else:
                inserted += 1
        logger.info(
            "mail_sync_recent_completed: fetched=%s inserted=%s updated=%s skipped_older=%s",
            fetched,
            inserted,
            updated,
            skipped_older,
        )
        return MailSyncResult(
            fetched=fetched,
            inserted=inserted,
            updated=updated,
            skipped_older=skipped_older,
        )

    def _load_latest_received_date(self) -> str:
        """
        로컬 DB의 최신 수신일시를 조회한다.

        Returns:
            최신 수신일시 문자열
        """
        if not self._db_path.exists():
            return ""
        with sqlite3.connect(str(self._db_path)) as connection:
            row = connection.execute("SELECT COALESCE(MAX(received_date), '') FROM emails").fetchone()
        return str(row[0] or "") if row is not None else ""

    def _should_skip_older_message(self, message: GraphMailMessage, latest_received_date: str) -> bool:
        """
        로컬 최신 메일보다 오래된 신규 메일인지 판별한다.

        Args:
            message: Graph 메일
            latest_received_date: 로컬 최신 수신일시

        Returns:
            skip 대상이면 True
        """
        if self._mail_service.read_mail_by_message_id(message.message_id) is not None:
            return False
        if not latest_received_date:
            return False
        return str(message.received_date or "") < str(latest_received_date or "")

    def _build_mail_record(self, message: GraphMailMessage) -> MailRecord:
        """
        Graph 메일을 MailRecord로 변환한다.

        Args:
            message: Graph 메일

        Returns:
            로컬 저장용 메일 레코드
        """
        return MailRecord(
            message_id=message.message_id,
            subject=message.subject,
            from_address=message.from_address,
            received_date=message.received_date,
            body_text=message.body_text,
            web_link=message.web_link,
        )
