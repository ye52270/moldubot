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
from app.services.mail_summary_queue_worker import MailSummaryQueueWorker

configure_logging()
logger = get_logger(__name__)


def parse_args() -> argparse.Namespace:
    """
    summary queue worker 스크립트 인자를 파싱한다.

    Returns:
        파싱된 인자 객체
    """
    parser = argparse.ArgumentParser(description="Process mail summary queue jobs")
    parser.add_argument("--db-path", default="data/sqlite/emails.db", help="SQLite DB path")
    parser.add_argument("--max-jobs", type=int, default=100, help="Max queue jobs per run")
    return parser.parse_args()


def main() -> None:
    """
    summary queue worker를 실행하고 결과를 로그로 출력한다.
    """
    args = parse_args()
    worker = MailSummaryQueueWorker(db_path=Path(str(args.db_path)))
    result = worker.process_many(max_jobs=int(args.max_jobs))
    payload = {
        "db_path": str(args.db_path),
        "max_jobs": int(args.max_jobs),
        "result": {
            "processed": result.processed,
            "failed": result.failed,
            "empty": result.empty,
        },
    }
    logger.info("summary_queue_worker_result: %s", json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    main()
