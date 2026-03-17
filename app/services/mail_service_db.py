from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any


def has_table_column(db_path: Path, table: str, column: str) -> bool:
    """지정 테이블에 컬럼이 존재하는지 확인한다."""
    if not db_path.exists():
        return False
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute(f"PRAGMA table_info({table})").fetchall()
        return any(str(row[1]).lower() == str(column).lower() for row in rows)
    finally:
        conn.close()


def fetch_latest_mail_row(db_path: Path, summary_select_clause: str, web_link_select_clause: str) -> dict[str, Any] | None:
    """DB에서 최신 메일 1건을 사전 형태로 조회한다."""
    if not db_path.exists():
        return None
    query = (
        "SELECT message_id, subject, from_address, received_date, "
        "COALESCE(body_clean, body_full, body_preview, '') AS body_text, "
        "COALESCE(body_full, body_clean, body_preview, '') AS code_body_text, "
        "COALESCE(body_full, '') AS body_full_text, "
        f"{summary_select_clause}, "
        f"{web_link_select_clause} "
        "FROM emails ORDER BY received_date DESC LIMIT 1"
    )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(query).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()


def fetch_mail_row_by_message_id(
    db_path: Path,
    message_id: str,
    summary_select_clause: str,
    web_link_select_clause: str,
) -> dict[str, Any] | None:
    """DB에서 `message_id`로 메일 1건을 조회한다."""
    if not db_path.exists():
        return None
    query = (
        "SELECT message_id, subject, from_address, received_date, "
        "COALESCE(body_clean, body_full, body_preview, '') AS body_text, "
        "COALESCE(body_full, body_clean, body_preview, '') AS code_body_text, "
        "COALESCE(body_full, '') AS body_full_text, "
        f"{summary_select_clause}, "
        f"{web_link_select_clause} "
        "FROM emails WHERE message_id = ? LIMIT 1"
    )
    conn = sqlite3.connect(str(db_path))
    conn.row_factory = sqlite3.Row
    try:
        row = conn.execute(query, (message_id,)).fetchone()
        return dict(row) if row is not None else None
    finally:
        conn.close()
