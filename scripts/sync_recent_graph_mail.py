from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parents[1]
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from app.integrations.microsoft_graph.mail_client import GraphMailClient
from app.services.mail_sync_service import MailSyncService


def parse_args() -> argparse.Namespace:
    """
    CLI 인자를 파싱한다.

    Returns:
        파싱된 네임스페이스
    """
    parser = argparse.ArgumentParser(description="Sync recent mail from Microsoft Graph into emails.db.")
    parser.add_argument(
        "--db-path",
        type=Path,
        default=ROOT_DIR / "data" / "sqlite" / "emails.db",
        help="SQLite database path",
    )
    parser.add_argument("--limit", type=int, default=20, help="Maximum number of messages to fetch")
    parser.add_argument("--dry-run", action="store_true", help="Print config only without Graph call")
    return parser.parse_args()


def main() -> int:
    """
    최근 Graph 메일 sync를 실행하고 JSON 결과를 출력한다.

    Returns:
        종료 코드
    """
    args = parse_args()
    client = GraphMailClient()
    if args.dry_run:
        payload = {
            "db_path": str(args.db_path),
            "limit": int(args.limit),
            "dry_run": True,
            "graph_configured": client.is_configured(),
        }
        json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
        sys.stdout.write("\n")
        return 0
    result = MailSyncService(db_path=args.db_path, graph_client=client).sync_recent_messages(limit=args.limit)
    payload = {
        "db_path": str(args.db_path),
        "limit": int(args.limit),
        "dry_run": False,
        **result.as_dict(),
    }
    json.dump(payload, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
