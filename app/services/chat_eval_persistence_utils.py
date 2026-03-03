from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def sanitize_timestamp(started_at: str) -> str:
    """파일명에 안전한 타임스탬프 문자열을 반환한다."""
    if not started_at:
        return datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H%M%S")
    normalized = started_at.replace(":", "").replace("-", "")
    normalized = normalized.replace("+", "_").replace(".", "_")
    return normalized[:22]


def persist_report(report: dict[str, Any], reports_dir: Path, latest_report_path: Path) -> None:
    """리포트를 최신/타임스탬프 파일로 저장한다."""
    reports_dir.mkdir(parents=True, exist_ok=True)
    started_at = str(report.get("meta", {}).get("started_at") or "")
    stamp = sanitize_timestamp(started_at=started_at)
    stamped_path = reports_dir / f"chat_eval_{stamp}.json"
    body = json.dumps(report, ensure_ascii=False, indent=2)
    latest_report_path.write_text(body, encoding="utf-8")
    stamped_path.write_text(body, encoding="utf-8")
