from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.logging_config import get_logger
from app.integrations.microsoft_graph.mail_client import GraphMailClient
from app.services.mail_service import MailRecord, MailService

logger = get_logger(__name__)


@dataclass
class MailContextResult:
    """
    선택 메일 컨텍스트 조회 결과 모델.

    Attributes:
        status: `completed` 또는 `failed`
        source: `db-cache` 또는 `graph-api` 또는 `not-found`
        mail: 조회된 메일 레코드
        reason: 실패 사유
    """

    status: str
    source: str
    mail: MailRecord | None
    reason: str = ""


class MailContextService:
    """
    `message_id` 기준 메일 컨텍스트를 DB/Graph에서 조회하는 서비스.
    """

    def __init__(self, db_path: Path, graph_client: GraphMailClient) -> None:
        """
        서비스 인스턴스를 초기화한다.

        Args:
            db_path: 로컬 SQLite 경로
            graph_client: Graph 조회 클라이언트
        """
        self._mail_service = MailService(db_path=db_path)
        self._graph_client = graph_client

    def get_mail_context(self, message_id: str, mailbox_user: str = "") -> MailContextResult:
        """
        선택 메일 컨텍스트를 조회한다.

        Args:
            message_id: Outlook/Graph 메시지 식별자
            mailbox_user: Graph 조회 대상 사용자 메일 주소

        Returns:
            조회 결과 모델
        """
        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id:
            return MailContextResult(status="failed", source="validation", mail=None, reason="message_id가 비어 있습니다.")

        cached_mail = self._mail_service.read_mail_by_message_id(message_id=normalized_message_id)
        if cached_mail is not None and not self._should_refresh_from_graph(
            cached_mail=cached_mail,
            mailbox_user=mailbox_user,
        ):
            cached_mail = self._ensure_summary_generated(mail=cached_mail)
            logger.info("선택 메일 컨텍스트 캐시 조회 성공: message_id=%s", normalized_message_id)
            return MailContextResult(status="completed", source="db-cache", mail=cached_mail)

        graph_mail = self._graph_client.get_message(
            mailbox_user=mailbox_user,
            message_id=normalized_message_id,
        )
        if graph_mail is None:
            return MailContextResult(
                status="failed",
                source="not-found",
                mail=None,
                reason="DB/Graph에서 메일을 찾지 못했습니다.",
            )

        mail = MailRecord(
            message_id=graph_mail.message_id,
            subject=graph_mail.subject,
            from_address=graph_mail.from_address,
            received_date=graph_mail.received_date,
            body_text=graph_mail.body_text,
            web_link=graph_mail.web_link,
        )
        self._mail_service.upsert_mail_record(mail=mail)
        mail = self._ensure_summary_generated(mail=mail)
        logger.info("선택 메일 컨텍스트 Graph 조회 성공: message_id=%s", normalized_message_id)
        return MailContextResult(status="completed", source="graph-api", mail=mail)

    def _should_refresh_from_graph(self, cached_mail: MailRecord, mailbox_user: str) -> bool:
        """
        코드 분석 정확도를 위해 Graph 재조회가 필요한지 판별한다.

        Args:
            cached_mail: DB 캐시 메일
            mailbox_user: 조회 대상 사용자 메일 주소

        Returns:
            Graph 재조회가 필요하면 True
        """
        if not str(mailbox_user or "").strip():
            return False
        body_full_text = str(cached_mail.body_full_text or "").strip()
        body_text = str(cached_mail.body_text or "").strip()
        return not body_full_text and bool(body_text)

    def _ensure_summary_generated(self, mail: MailRecord) -> MailRecord:
        """
        summary가 비어 있으면 queue worker를 즉시 실행해 보강한다.

        Args:
            mail: 보강 대상 메일

        Returns:
            summary 보강 시도 후 최신 메일 레코드
        """
        if str(mail.summary_text or "").strip():
            return mail
        refreshed = self._mail_service.ensure_summary_for_message(
            message_id=str(mail.message_id or "").strip(),
            requested_by="mail_context",
            max_attempts=3,
        )
        return refreshed if refreshed is not None else mail

    def run_post_action(self, action: str, summary_line_target: int) -> dict[str, Any]:
        """
        현재 메일 컨텍스트 기준 후속 작업을 공통 경로로 실행한다.

        Args:
            action: 후속작업 종류
            summary_line_target: 요약 라인 목표

        Returns:
            후속작업 실행 결과 사전
        """
        return self._mail_service.run_post_action(
            action=action,
            summary_line_target=summary_line_target,
        )


def build_mail_context_service(db_path: Path) -> MailContextService:
    """
    MailContextService를 생성한다.

    Args:
        db_path: SQLite DB 경로

    Returns:
        MailContextService 인스턴스
    """
    return MailContextService(db_path=db_path, graph_client=GraphMailClient())
