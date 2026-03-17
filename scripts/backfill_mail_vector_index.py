from __future__ import annotations

import argparse
import json
import os
import sqlite3
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.services.mail_vector_index_service import MailVectorIndexService


def parse_args() -> argparse.Namespace:
    """
    벡터 인덱스 재색인 스크립트 인자를 파싱한다.

    Returns:
        파싱된 인자 객체
    """
    parser = argparse.ArgumentParser(description="Backfill mail vector index from emails.db")
    parser.add_argument("--db-path", type=Path, default=ROOT_DIR / "data" / "sqlite" / "emails.db")
    parser.add_argument("--vector-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    """
    기존 emails 레코드를 벡터 인덱스로 재색인한다.

    Returns:
        프로세스 종료 코드
    """
    args = parse_args()
    if args.vector_dir is not None:
        os.environ["MOLDUBOT_MAIL_VECTOR_DIR"] = str(args.vector_dir)
    service = MailVectorIndexService()
    indexed = backfill_vectors(db_path=args.db_path, service=service)
    payload = {
        "db_path": str(args.db_path),
        "vector_dir": str(args.vector_dir or service.get_status().persist_dir),
        "indexed": indexed,
        "backend": service.get_status().backend,
    }
    json.dump(payload, sys.stdout, ensure_ascii=False)
    sys.stdout.write("\n")
    return 0


def backfill_vectors(db_path: Path, service: MailVectorIndexService) -> int:
    """
    emails 테이블 전건을 벡터 인덱스로 upsert한다.

    Args:
        db_path: source emails DB 경로
        service: 벡터 인덱스 서비스

    Returns:
        upsert 성공 건수
    """
    if not db_path.exists():
        return 0
    connection = sqlite3.connect(str(db_path))
    try:
        rows = connection.execute(
            "SELECT message_id, COALESCE(subject, ''), COALESCE(body_clean, body_full, body_preview, ''), "
            "COALESCE(summary, ''), COALESCE(category, ''), COALESCE(from_address, ''), COALESCE(received_date, '') "
            "FROM emails ORDER BY received_date DESC"
        ).fetchall()
    finally:
        connection.close()
    indexed = 0
    for row in rows:
        if service.upsert_mail_document(
            message_id=str(row[0] or ""),
            subject=str(row[1] or ""),
            body_text=str(row[2] or ""),
            summary=str(row[3] or ""),
            category=str(row[4] or ""),
            from_address=str(row[5] or ""),
            received_date=str(row[6] or ""),
        ):
            indexed += 1
    return indexed


if __name__ == "__main__":
    raise SystemExit(main())
