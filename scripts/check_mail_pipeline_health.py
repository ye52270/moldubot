from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from pathlib import Path
from typing import Any

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.mail_vector_index_service import MailVectorIndexService


def parse_args() -> argparse.Namespace:
    """
    CLI 인자를 파싱한다.

    Returns:
        파싱된 argparse 네임스페이스
    """
    parser = argparse.ArgumentParser(description="Inspect mail ingestion, queue, and Chroma health.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT_DIR / "data" / "sqlite" / "emails.db",
        help="SQLite database path",
    )
    return parser.parse_args()


def main() -> int:
    """
    메일 파이프라인 상태를 JSON으로 출력한다.

    Returns:
        프로세스 종료 코드
    """
    args = parse_args()
    payload = build_health_payload(db_path=args.db_path)
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


def build_health_payload(db_path: Path) -> dict[str, Any]:
    """
    메일 파이프라인 상태 페이로드를 생성한다.

    Args:
        db_path: 점검 대상 SQLite 경로

    Returns:
        JSON 직렬화 가능한 상태 사전
    """
    return {
        "db_path": str(db_path),
        "db_exists": db_path.exists(),
        "emails": load_email_stats(db_path=db_path),
        "queue": load_queue_stats(db_path=db_path),
        "graph_subscription": load_subscription_settings(db_path=db_path),
        "vector_index": MailVectorIndexService().get_status().as_dict(),
    }


def load_email_stats(db_path: Path) -> dict[str, Any]:
    """
    메일 테이블의 기본 집계를 조회한다.

    Args:
        db_path: SQLite 경로

    Returns:
        메일 집계 사전
    """
    if not db_path.exists():
        return {"count": 0, "missing_summary_count": 0, "latest_received_date": ""}
    with sqlite3.connect(str(db_path)) as connection:
        return {
            "count": fetch_scalar(connection, "SELECT COUNT(*) FROM emails", 0),
            "missing_summary_count": fetch_scalar(
                connection,
                "SELECT COUNT(*) FROM emails WHERE COALESCE(summary, '') = ''",
                0,
            ),
            "latest_received_date": fetch_scalar(
                connection,
                "SELECT COALESCE(MAX(received_date), '') FROM emails",
                "",
            ),
        }


def load_queue_stats(db_path: Path) -> dict[str, Any]:
    """
    summary queue 상태 집계를 조회한다.

    Args:
        db_path: SQLite 경로

    Returns:
        queue 집계 사전
    """
    if not db_path.exists():
        return {"count": 0, "by_status": {}}
    with sqlite3.connect(str(db_path)) as connection:
        rows = connection.execute(
            "SELECT status, COUNT(*) FROM mail_summary_queue GROUP BY status ORDER BY status"
        ).fetchall()
    return {
        "count": sum(int(row[1]) for row in rows),
        "by_status": {str(row[0] or ""): int(row[1]) for row in rows},
    }


def load_subscription_settings(db_path: Path) -> dict[str, str]:
    """
    Graph subscription 관련 설정값을 조회한다.

    Args:
        db_path: SQLite 경로

    Returns:
        subscription 설정 사전
    """
    if not db_path.exists():
        return {
            "mail_subscription_expiration": "",
            "mail_subscription_notification_url": "",
        }
    with sqlite3.connect(str(db_path)) as connection:
        rows = connection.execute(
            "SELECT key, value FROM sync_settings WHERE key IN (?, ?)",
            ("mail_subscription_expiration", "mail_subscription_notification_url"),
        ).fetchall()
    mapping = {str(row[0]): str(row[1] or "") for row in rows}
    return {
        "mail_subscription_expiration": mapping.get("mail_subscription_expiration", ""),
        "mail_subscription_notification_url": mapping.get("mail_subscription_notification_url", ""),
    }


def fetch_scalar(connection: sqlite3.Connection, query: str, default: Any) -> Any:
    """
    단일 값을 반환하는 SQL을 안전하게 실행한다.

    Args:
        connection: SQLite 연결
        query: 실행할 SELECT 쿼리
        default: 값이 없을 때 기본값

    Returns:
        조회된 값 또는 기본값
    """
    row = connection.execute(query).fetchone()
    if row is None:
        return default
    return row[0] if row[0] is not None else default


if __name__ == "__main__":
    raise SystemExit(main())
