from __future__ import annotations

import sqlite3
from contextvars import ContextVar
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from app.core.logging_config import get_logger
from app.services.mail_service_utils import (
    build_mail_context_payload,
    build_mail_record_from_row,
    build_upsert_insert_query,
    build_upsert_update_query,
)
from app.services.mail_text_utils import (
    extract_recipients_from_body,
    select_salient_summary_sentences,
    trim_sentence,
)

logger = get_logger(__name__)


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
        summary_text: 사전 생성된 요약 텍스트
        web_link: Outlook Web 링크
    """

    message_id: str
    subject: str
    from_address: str
    received_date: str
    body_text: str
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
        update_query = build_upsert_update_query(include_web_link=include_web_link)
        insert_query = build_upsert_insert_query(include_web_link=include_web_link)
        body_preview = mail.body_text[:400]
        conn = sqlite3.connect(str(self._db_path))
        try:
            update_params = (
                (
                    mail.subject,
                    mail.from_address,
                    mail.received_date,
                    body_preview,
                    mail.body_text,
                    mail.body_text,
                    mail.web_link,
                    mail.message_id,
                )
                if include_web_link
                else (
                    mail.subject,
                    mail.from_address,
                    mail.received_date,
                    body_preview,
                    mail.body_text,
                    mail.body_text,
                    mail.message_id,
                )
            )
            updated = conn.execute(
                update_query,
                update_params,
            )
            if updated.rowcount == 0:
                insert_params = (
                    (
                        mail.message_id,
                        mail.subject,
                        mail.from_address,
                        mail.received_date,
                        body_preview,
                        mail.body_text,
                        mail.body_text,
                        mail.web_link,
                    )
                    if include_web_link
                    else (
                        mail.message_id,
                        mail.subject,
                        mail.from_address,
                        mail.received_date,
                        body_preview,
                        mail.body_text,
                        mail.body_text,
                    )
                )
                conn.execute(
                    insert_query,
                    insert_params,
                )
            conn.commit()
        finally:
            conn.close()

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

    def run_post_action(self, action: str, summary_line_target: int) -> dict[str, Any]:
        """
        메일 조회 후속작업을 단일 경로로 실행한다.

        Args:
            action: 후속작업 종류(`current_mail`, `summary`, `report`, `key_facts`, `recipients`, `summary_with_key_facts`)
            summary_line_target: 요약 라인 목표

        Returns:
            실행 결과 사전
        """
        normalized_action = str(action or "").strip().lower()
        if normalized_action == "current_mail":
            mail = self.get_current_mail()
            if mail is None:
                return {"action": "current_mail", "status": "failed", "reason": "현재 메일을 찾지 못했습니다."}
            return {
                "action": "current_mail",
                "status": "completed",
                "message_id": mail.message_id,
                "subject": mail.subject,
                "from_address": mail.from_address,
                "received_date": mail.received_date,
                "body_preview": mail.body_text[:400],
                "mail_context": build_mail_context_payload(mail=mail),
            }
        return self._build_context_only_post_action_payload(action=normalized_action)

    def extract_key_facts(self, limit: int = 5) -> list[str]:
        """
        현재 메일에서 핵심 포인트를 추출한다.

        Args:
            limit: 최대 추출 개수

        Returns:
            핵심 포인트 문자열 목록
        """
        mail = self.get_current_mail()
        if mail is None:
            return ["현재 메일이 없습니다."]
        fact_lines = select_salient_summary_sentences(text=mail.body_text, line_target=max(1, limit * 2))
        if not fact_lines:
            return ["핵심 추출 대상 본문이 없습니다."]
        markers = ("요청", "일정", "회의", "마감", "필요", "확인", "공유", "중요")
        prioritized = [item for item in fact_lines if any(mark in item for mark in markers)]
        base = prioritized or fact_lines
        return [trim_sentence(sentence=item) for item in base[: max(1, limit)]]

    def extract_recipients(self, limit: int = 10) -> list[str]:
        """
        현재 메일 본문 헤더(`To:`) 기준으로 수신자 목록을 추출한다.

        Args:
            limit: 최대 반환 개수

        Returns:
            수신자 문자열 목록
        """
        mail = self.get_current_mail()
        if mail is None:
            return ["현재 메일이 없습니다."]
        recipients = extract_recipients_from_body(text=mail.body_text)
        if not recipients:
            return ["수신자 정보를 본문에서 찾지 못했습니다."]
        return recipients[: max(1, limit)]

    def _fetch_latest_mail_row(self) -> dict[str, Any] | None:
        """
        DB에서 최신 메일 1건을 사전 형태로 조회한다.

        Returns:
            메일 행 사전 또는 None
        """
        if not self._db_path.exists():
            logger.error("메일 DB 파일이 없습니다: %s", self._db_path)
            return None

        query = (
            "SELECT message_id, subject, from_address, received_date, "
            "COALESCE(body_clean, body_full, body_preview, '') AS body_text, "
            f"{self._summary_select_clause()}, "
            f"{self._web_link_select_clause()} "
            "FROM emails ORDER BY received_date DESC LIMIT 1"
        )
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(query).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

    def _fetch_mail_row_by_message_id(self, message_id: str) -> dict[str, Any] | None:
        """
        DB에서 `message_id`로 메일 1건을 조회한다.

        Args:
            message_id: 메시지 식별자

        Returns:
            메일 행 사전 또는 None
        """
        if not self._db_path.exists():
            logger.error("메일 DB 파일이 없습니다: %s", self._db_path)
            return None
        query = (
            "SELECT message_id, subject, from_address, received_date, "
            "COALESCE(body_clean, body_full, body_preview, '') AS body_text, "
            f"{self._summary_select_clause()}, "
            f"{self._web_link_select_clause()} "
            "FROM emails WHERE message_id = ? LIMIT 1"
        )
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(query, (message_id,)).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()

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

        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute("PRAGMA table_info(emails)").fetchall()
            has_column = any(str(row[1]).lower() == "summary" for row in rows)
            self._has_summary_column_cache = has_column
            return has_column
        finally:
            conn.close()

    def _build_context_only_post_action_payload(self, action: str) -> dict[str, Any]:
        """
        메일 후속 액션 요청에 대해 context-only 페이로드를 생성한다.

        Args:
            action: 요청된 후속 액션 이름

        Returns:
            context-only 실행 결과 사전
        """
        mail = self.get_current_mail()
        return {
            "action": action or "summary",
            "status": "context_only",
            "mail_context": build_mail_context_payload(mail=mail),
        }

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
        conn = sqlite3.connect(str(self._db_path))
        try:
            rows = conn.execute("PRAGMA table_info(emails)").fetchall()
            has_column = any(str(row[1]).lower() == "web_link" for row in rows)
            self._has_web_link_column_cache = has_column
            return has_column
        finally:
            conn.close()
