from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

from app.core.logging_config import get_logger

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
    """

    message_id: str
    subject: str
    from_address: str
    received_date: str
    body_text: str


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
        self._lock = Lock()
        self._current_mail: MailRecord | None = None

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

        mail = MailRecord(
            message_id=str(row["message_id"] or ""),
            subject=str(row["subject"] or ""),
            from_address=str(row["from_address"] or ""),
            received_date=str(row["received_date"] or ""),
            body_text=str(row["body_text"] or ""),
        )
        with self._lock:
            self._current_mail = mail
        return mail

    def get_current_mail(self) -> MailRecord | None:
        """
        현재 캐시된 메일을 반환한다. 없으면 최근 메일을 새로 조회한다.

        Returns:
            현재 메일 레코드 또는 None
        """
        with self._lock:
            cached = self._current_mail
        if cached is not None:
            return cached
        return self.read_current_mail()

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
        target = _normalize_line_target(line_target=line_target)
        sentences = _split_sentences(text=mail.body_text)
        if not sentences:
            return ["본문이 비어 있어 요약할 수 없습니다."]
        return [_trim_sentence(sentence=item) for item in sentences[:target]]

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
        sentences = _split_sentences(text=mail.body_text)
        if not sentences:
            return ["핵심 추출 대상 본문이 없습니다."]
        markers = ("요청", "일정", "회의", "마감", "필요", "확인", "공유", "중요")
        prioritized = [item for item in sentences if any(mark in item for mark in markers)]
        base = prioritized or sentences
        return [_trim_sentence(sentence=item) for item in base[: max(1, limit)]]

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
        recipients = _extract_recipients_from_body(text=mail.body_text)
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
            "COALESCE(body_clean, body_full, body_preview, '') AS body_text "
            "FROM emails ORDER BY received_date DESC LIMIT 1"
        )
        conn = sqlite3.connect(str(self._db_path))
        conn.row_factory = sqlite3.Row
        try:
            row = conn.execute(query).fetchone()
            return dict(row) if row is not None else None
        finally:
            conn.close()


def _normalize_line_target(line_target: int) -> int:
    """
    요약 라인 목표값을 안전 범위(1~20)로 보정한다.

    Args:
        line_target: 입력 라인 목표값

    Returns:
        보정된 라인 목표값
    """
    if line_target < 1:
        return 1
    if line_target > 20:
        return 20
    return line_target


def _split_sentences(text: str) -> list[str]:
    """
    본문 문자열을 문장/행 단위로 분리한다.

    Args:
        text: 원본 본문 텍스트

    Returns:
        비어 있지 않은 문장 목록
    """
    cleaned = re.sub(r"\r", "\n", str(text or ""))
    line_chunks = [item.strip() for item in cleaned.split("\n") if item and item.strip()]

    sentences: list[str] = []
    for chunk in line_chunks:
        # 이메일 주소 점(.) 분할을 피하기 위해 문장부호 + 공백 패턴만 분리한다.
        parts = re.split(r"(?<=[가-힣A-Za-z0-9])[.!?]\s+", chunk)
        for part in parts:
            normalized = part.strip()
            if normalized:
                sentences.append(normalized)
    return sentences


def _trim_sentence(sentence: str, max_len: int = 140) -> str:
    """
    문장을 최대 길이로 자른다.

    Args:
        sentence: 원본 문장
        max_len: 최대 길이

    Returns:
        길이 제한이 적용된 문장
    """
    text = sentence.strip()
    if len(text) <= max_len:
        return text
    return text[: max_len - 1].rstrip() + "…"


def _extract_recipients_from_body(text: str) -> list[str]:
    """
    메일 본문 헤더 중 `To:` 구간에서 수신자 문자열을 파싱한다.

    Args:
        text: 메일 본문

    Returns:
        파싱된 수신자 목록
    """
    normalized = str(text or "").replace("\r", "\n")
    match = re.search(r"To:\s*(.+?)(?:Cc:|Subject:|From:|$)", normalized, flags=re.IGNORECASE | re.DOTALL)
    if not match:
        return []

    raw = match.group(1).replace("\n", " ")
    parts = re.split(r"[;,]", raw)
    recipients = [item.strip() for item in parts if item and item.strip()]

    deduped: list[str] = []
    for recipient in recipients:
        if recipient not in deduped:
            deduped.append(recipient)
    return deduped
