from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from dotenv import load_dotenv

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))
load_dotenv(dotenv_path=ROOT_DIR / ".env")

from app.core.logging_config import configure_logging, get_logger
from app.services.mail_summary_queue_service import MailSummaryQueueService

configure_logging()
logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """
    summary backfill enqueue 스크립트 인자를 파싱한다.

    Returns:
        파싱된 인자 객체
    """
    parser = argparse.ArgumentParser(description="Enqueue summary backfill jobs")
    parser.add_argument("--db-path", default="data/sqlite/emails.db", help="SQLite DB path")
    parser.add_argument("--limit", type=int, default=0, help="Max rows to scan (0 means all)")
    parser.add_argument(
        "--include-existing",
        action="store_true",
        help="Enqueue rows even when summary is already populated",
    )
    return parser.parse_args()


def main() -> None:
    """
    summary backfill enqueue를 실행하고 결과를 로그로 출력한다.
    """
    args = parse_args()
    service = MailSummaryQueueService(db_path=Path(str(args.db_path)))
    result = service.enqueue_backfill(
        limit=int(args.limit),
        include_existing=bool(args.include_existing),
    )
    payload = {
        "db_path": str(args.db_path),
        "limit": int(args.limit),
        "include_existing": bool(args.include_existing),
        "result": {
            "scanned": result.scanned,
            "enqueued": result.enqueued,
            "skipped_existing": result.skipped_existing,
        },
    }
    logger.info("summary_backfill_enqueue_result: %s", json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
