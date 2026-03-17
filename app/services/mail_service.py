from __future__ import annotations

import os
import sqlite3
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.logging_config import get_logger
from app.services.mail_service_utils import (
    build_mail_record_from_row,
    build_upsert_insert_query,
    build_upsert_update_query,
)
from app.services.mail_service_db import fetch_latest_mail_row, fetch_mail_row_by_message_id, has_table_column
from app.services.mail_service_actions import (
    build_context_only_post_action_payload,
    build_current_mail_post_action_payload,
    extract_key_facts_from_mail,
    extract_recipients_from_mail,
)
from app.services.mail_summary_queue_service import MailSummaryQueueService
from app.services.mail_text_utils import select_salient_summary_sentences

logger = get_logger(__name__)
SUMMARY_SYNC_ON_UPSERT_ENV = "MOLDUBOT_SUMMARY_SYNC_ON_UPSERT"


@dataclass
class MailRecord:
    """
    메일 레코드 표준 데이터 구조.

    Attributes:
        message_id: 메일 메시지 식별자
        subject: 제목
        from_address: 발신자 주소/표시명
        received_date: 수신 일시 문자열
        body_text: 본문 텍스트
        code_body_text: 코드 분석용 본문 텍스트(`body_full` 우선)
        body_full_text: DB 원문 본문(`body_full`) 텍스트
        summary_text: 사전 생성된 요약 텍스트
        web_link: Outlook Web 링크
    """

    message_id: str
    subject: str
    from_address: str
    received_date: str
    body_text: str
    code_body_text: str = ""
    body_full_text: str = ""
    summary_text: str = ""
    web_link: str = ""


class MailService:
    """
    로컬 SQLite(`emails.db`) 기반 메일 조회/요약/추출 서비스를 제공한다.
    """

    def __init__(self, db_path: Path) -> None:
        """
        메일 서비스 인스턴스를 초기화한다.

        Args:
            db_path: SQLite DB 경로
        """
        self._db_path = db_path
        self._current_mail_ctx: ContextVar[MailRecord | None] = ContextVar(
            "mail_service_current_mail",
            default=None,
        )
        self._has_summary_column_cache: bool | None = None
        self._has_web_link_column_cache: bool | None = None
        self._summary_queue_service = MailSummaryQueueService(db_path=db_path)
        self._summary_sync_on_upsert = _is_enabled(value=str(os.getenv(SUMMARY_SYNC_ON_UPSERT_ENV, "1")))
        logger.info(
            "mail_service.summary_sync_on_upsert: enabled=%s db_path=%s pid=%s",
            self._summary_sync_on_upsert,
            self._db_path,
            os.getpid(),
        )

    def read_current_mail(self) -> MailRecord | None:
        """
        가장 최근 메일을 조회하고 현재 메일 캐시에 저장한다.

        Returns:
            최근 메일 레코드. 조회 실패 시 None
        """
        row = self._fetch_latest_mail_row()
        if row is None:
            logger.warning("현재 메일 조회 실패: 데이터가 없습니다.")
            return None

        mail = build_mail_record_from_row(row=row)
        self._current_mail_ctx.set(mail)
        return mail

    def read_mail_by_message_id(self, message_id: str) -> MailRecord | None:
        """
        지정한 `message_id`로 메일 1건을 조회하고 현재 메일 캐시에 저장한다.

        Args:
            message_id: 조회 대상 메시지 식별자

        Returns:
            메일 레코드 또는 None
        """
        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id:
            return None
        row = self._fetch_mail_row_by_message_id(message_id=normalized_message_id)
        if row is None:
            return None
        mail = build_mail_record_from_row(row=row)
        self.set_current_mail(mail=mail)
        return mail

    def get_current_mail(self) -> MailRecord | None:
        """
        현재 캐시된 메일을 반환한다.

        Returns:
            현재 메일 레코드 또는 None
        """
        return self._current_mail_ctx.get()

    def set_current_mail(self, mail: MailRecord) -> None:
        """
        현재 메일 캐시를 지정 레코드로 갱신한다.

        Args:
            mail: 캐시에 저장할 메일 레코드
        """
        self._current_mail_ctx.set(mail)

    def clear_current_mail(self) -> None:
        """
        현재 메일 캐시를 비운다.
        """
        self._current_mail_ctx.set(None)

    def upsert_mail_record(self, mail: MailRecord) -> None:
        """
        메일 레코드를 `message_id` 기준으로 upsert한다.

        Args:
            mail: 저장 대상 메일 레코드
        """
        if not self._db_path.exists():
            logger.warning("메일 DB 파일이 없어 upsert를 건너뜁니다: %s", self._db_path)
            return
        include_web_link = self._has_web_link_column()
        include_summary = self._has_summary_column()
        update_query = build_upsert_update_query(
            include_web_link=include_web_link,
            include_summary=include_summary,
        )
        insert_query = build_upsert_insert_query(
            include_web_link=include_web_link,
            include_summary=include_summary,
        )
        body_preview = mail.body_text[:400]
        summary_text = str(mail.summary_text or "").strip()
        conn = sqlite3.connect(str(self._db_path))
        try:
            update_params = self._build_upsert_update_params(
                mail=mail,
                body_preview=body_preview,
                summary_text=summary_text,
                include_web_link=include_web_link,
                include_summary=include_summary,
            )
            updated = conn.execute(
                update_query,
                update_params,
            )
            if updated.rowcount == 0:
                insert_params = self._build_upsert_insert_params(
                    mail=mail,
                    body_preview=body_preview,
                    summary_text=summary_text,
                    include_web_link=include_web_link,
                    include_summary=include_summary,
                )
                conn.execute(
                    insert_query,
                    insert_params,
                )
            conn.commit()
        finally:
            conn.close()
        if include_summary and not summary_text:
            queued = self._summary_queue_service.enqueue_message(
                message_id=mail.message_id,
                requested_by="upsert",
            )
            if queued and self._summary_sync_on_upsert:
                self._process_summary_queue_once()

    def _process_summary_queue_once(self) -> None:
        """
        upsert 직후 summary queue 작업 1건을 동기 실행한다.
        """
        from app.services.mail_summary_queue_worker import MailSummaryQueueWorker

        worker = MailSummaryQueueWorker(db_path=self._db_path)
        worker.process_once()

    def ensure_summary_for_message(
        self,
        message_id: str,
        requested_by: str = "mail_context",
        max_attempts: int = 3,
    ) -> MailRecord | None:
        """
        특정 message_id의 summary/category가 비어 있으면 즉시 생성 시도를 수행한다.

        Args:
            message_id: 대상 message_id
            requested_by: queue 적재 요청자 태그
            max_attempts: worker 처리 최대 시도 횟수

        Returns:
            summary 보강 후 최신 메일 레코드(없으면 None)
        """
        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id:
            return None
        current = self.read_mail_by_message_id(message_id=normalized_message_id)
        if current is None or not self.supports_summary_storage():
            return current
        if str(current.summary_text or "").strip():
            return current
        self._summary_queue_service.enqueue_message(
            message_id=normalized_message_id,
            requested_by=str(requested_by or "mail_context").strip(),
            force_requeue=True,
        )
        for _ in range(max(1, int(max_attempts))):
            self._process_summary_queue_once()
            refreshed = self.read_mail_by_message_id(message_id=normalized_message_id)
            if refreshed is not None and str(refreshed.summary_text or "").strip():
                return refreshed
        return current

    def _build_upsert_update_params(
        self,
        mail: MailRecord,
        body_preview: str,
        summary_text: str,
        include_web_link: bool,
        include_summary: bool,
    ) -> tuple[str, ...]:
        """
        UPDATE upsert SQL 파라미터를 생성한다.

        Args:
            mail: 저장 대상 메일 레코드
            body_preview: 본문 미리보기
            summary_text: 저장 summary 텍스트
            include_web_link: web_link 컬럼 포함 여부
            include_summary: summary 컬럼 포함 여부

        Returns:
            UPDATE 파라미터 튜플
        """
        base_params = (
            mail.subject,
            mail.from_address,
            mail.received_date,
            body_preview,
            mail.body_text,
            mail.body_text,
        )
        if include_summary and include_web_link:
            return base_params + (summary_text, mail.web_link, mail.message_id)
        if include_summary:
            return base_params + (summary_text, mail.message_id)
        if include_web_link:
            return base_params + (mail.web_link, mail.message_id)
        return base_params + (mail.message_id,)

    def _build_upsert_insert_params(
        self,
        mail: MailRecord,
        body_preview: str,
        summary_text: str,
        include_web_link: bool,
        include_summary: bool,
    ) -> tuple[str, ...]:
        """
        INSERT upsert SQL 파라미터를 생성한다.

        Args:
            mail: 저장 대상 메일 레코드
            body_preview: 본문 미리보기
            summary_text: 저장 summary 텍스트
            include_web_link: web_link 컬럼 포함 여부
            include_summary: summary 컬럼 포함 여부

        Returns:
            INSERT 파라미터 튜플
        """
        base_params = (
            mail.message_id,
            mail.subject,
            mail.from_address,
            mail.received_date,
            body_preview,
            mail.body_text,
            mail.body_text,
        )
        if include_summary and include_web_link:
            return base_params + (summary_text, mail.web_link)
        if include_summary:
            return base_params + (summary_text,)
        if include_web_link:
            return base_params + (mail.web_link,)
        return base_params

    def summarize_current_mail(self, line_target: int) -> list[str]:
        """
        현재 메일 본문을 목표 줄 수에 맞춰 요약한다.

        Args:
            line_target: 요약 줄 수 목표

        Returns:
            요약 라인 목록
        """
        mail = self.get_current_mail()
        if mail is None:
            return ["현재 메일이 없습니다."]
        summary_lines = select_salient_summary_sentences(
            text=mail.body_text,
            line_target=line_target,
        )
        if not summary_lines:
            return ["본문이 비어 있어 요약할 수 없습니다."]
        return summary_lines

    def run_post_action(self, action: str) -> dict[str, Any]:
        """
        메일 조회 후속작업을 단일 경로로 실행한다.

        Args:
            action: 후속작업 종류(`current_mail`, `summary`, `report`, `key_facts`, `recipients`, `summary_with_key_facts`)
        Returns:
            실행 결과 사전
        """
        normalized_action = str(action or "").strip().lower()
        if normalized_action == "current_mail":
            return build_current_mail_post_action_payload(mail=self.get_current_mail())
        return self._build_context_only_post_action_payload(action=normalized_action)

    def extract_key_facts(self, limit: int = 5) -> list[str]:
        """
        현재 메일에서 핵심 포인트를 추출한다.

        Args:
            limit: 최대 추출 개수

        Returns:
            핵심 포인트 문자열 목록
        """
        return extract_key_facts_from_mail(mail=self.get_current_mail(), limit=limit)

    def extract_recipients(self, limit: int = 10) -> list[str]:
        """
        현재 메일 본문 헤더(`To:`) 기준으로 수신자 목록을 추출한다.

        Args:
            limit: 최대 반환 개수

        Returns:
            수신자 문자열 목록
        """
        return extract_recipients_from_mail(mail=self.get_current_mail(), limit=limit)

    def _fetch_latest_mail_row(self) -> dict[str, Any] | None:
        """DB에서 최신 메일 1건을 사전 형태로 조회한다."""
        row = fetch_latest_mail_row(
            db_path=self._db_path,
            summary_select_clause=self._summary_select_clause(),
            web_link_select_clause=self._web_link_select_clause(),
        )
        if row is None and not self._db_path.exists():
            logger.error("메일 DB 파일이 없습니다: %s", self._db_path)
        return row

    def _fetch_mail_row_by_message_id(self, message_id: str) -> dict[str, Any] | None:
        """DB에서 `message_id`로 메일 1건을 조회한다."""
        row = fetch_mail_row_by_message_id(
            db_path=self._db_path,
            message_id=message_id,
            summary_select_clause=self._summary_select_clause(),
            web_link_select_clause=self._web_link_select_clause(),
        )
        if row is None and not self._db_path.exists():
            logger.error("메일 DB 파일이 없습니다: %s", self._db_path)
        return row

    def _summary_select_clause(self) -> str:
        """
        summary 컬럼 지원 여부에 따라 SELECT 절 별칭을 반환한다.

        Returns:
            summary_text 별칭 SQL 조각
        """
        if self._has_summary_column():
            return "COALESCE(summary, '') AS summary_text"
        return "'' AS summary_text"

    def _has_summary_column(self) -> bool:
        """
        emails 테이블에 `summary` 컬럼이 존재하는지 확인한다.

        Returns:
            summary 컬럼이 있으면 True
        """
        cached = self._has_summary_column_cache
        if cached is not None:
            return cached
        if not self._db_path.exists():
            self._has_summary_column_cache = False
            return False

        has_column = has_table_column(db_path=self._db_path, table="emails", column="summary")
        self._has_summary_column_cache = has_column
        return has_column

    def supports_summary_storage(self) -> bool:
        """
        emails 테이블의 summary 저장 지원 여부를 반환한다.

        Returns:
            summary 컬럼이 존재하면 True
        """
        return self._has_summary_column()

    def _build_context_only_post_action_payload(self, action: str) -> dict[str, Any]:
        """
        메일 후속 액션 요청에 대해 context-only 페이로드를 생성한다.

        Args:
            action: 요청된 후속 액션 이름

        Returns:
            context-only 실행 결과 사전
        """
        return build_context_only_post_action_payload(action=action, mail=self.get_current_mail())

    def _web_link_select_clause(self) -> str:
        """
        web_link 컬럼 지원 여부에 따라 SELECT 절 별칭을 반환한다.

        Returns:
            web_link 별칭 SQL 조각
        """
        if self._has_web_link_column():
            return "COALESCE(web_link, '') AS web_link"
        return "'' AS web_link"

    def _has_web_link_column(self) -> bool:
        """
        emails 테이블에 `web_link` 컬럼이 존재하는지 확인한다.

        Returns:
            web_link 컬럼이 있으면 True
        """
        cached = self._has_web_link_column_cache
        if cached is not None:
            return cached
        if not self._db_path.exists():
            self._has_web_link_column_cache = False
            return False
        has_column = has_table_column(db_path=self._db_path, table="emails", column="web_link")
        self._has_web_link_column_cache = has_column
        return has_column


def _is_enabled(value: str) -> bool:
    """
    환경변수 활성화 문자열을 bool로 변환한다.

    Args:
        value: 환경변수 값

    Returns:
        활성화 여부
    """
    return str(value or "").strip().lower() not in {"0", "false", "off", "no"}
