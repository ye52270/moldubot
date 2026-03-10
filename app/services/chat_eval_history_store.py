from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.core.logging_config import get_logger

logger = get_logger(__name__)

ROOT_DIR = Path(__file__).resolve().parents[2]
DB_PATH = ROOT_DIR / "data" / "reports" / "chat_eval_history.sqlite3"


def record_chat_eval_run(report: dict[str, Any]) -> int:
    """
    Chat Eval 실행 결과를 SQLite에 차수(run_no) 단위로 저장한다.

    Args:
        report: `run_chat_eval_session`가 생성한 리포트 객체

    Returns:
        저장된 실행 차수(run_no)
    """
    _ensure_schema()
    meta = report.get("meta", {}) if isinstance(report, dict) else {}
    summary = report.get("summary", {}) if isinstance(report, dict) else {}
    cases = report.get("cases", []) if isinstance(report, dict) else []

    started_at = str(meta.get("started_at") or "")
    finished_at = str(meta.get("finished_at") or "")
    chat_url = str(meta.get("chat_url") or "")
    judge_model = str(meta.get("judge_model") or "")
    selected_case_count = int(meta.get("selected_case_count") or 0)
    pass_rate = float(summary.get("judge_pass_rate") or 0.0)
    avg_score = float(summary.get("avg_judge_score") or 0.0)
    created_at = datetime.now(tz=timezone.utc).isoformat()
    report_json = json.dumps(report, ensure_ascii=False)

    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            (
                "INSERT INTO eval_runs "
                "(started_at, finished_at, chat_url, judge_model, selected_case_count, pass_rate, avg_score, report_json, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                started_at,
                finished_at,
                chat_url,
                judge_model,
                selected_case_count,
                pass_rate,
                avg_score,
                report_json,
                created_at,
            ),
        )
        run_no = int(cursor.lastrowid or 0)
        _insert_case_rows(cursor=cursor, run_no=run_no, cases=cases)
        conn.commit()

    logger.info("chat_eval.history.saved: run_no=%s cases=%s", run_no, len(cases) if isinstance(cases, list) else 0)
    return run_no


def list_chat_eval_runs(limit: int = 20) -> list[dict[str, Any]]:
    """
    최근 Chat Eval 실행 이력 요약을 조회한다.

    Args:
        limit: 조회할 최대 건수

    Returns:
        실행 이력 요약 목록
    """
    _ensure_schema()
    normalized_limit = max(1, min(int(limit or 20), 200))
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            (
                "SELECT run_no, started_at, finished_at, judge_model, selected_case_count, pass_rate, avg_score, created_at "
                "FROM eval_runs ORDER BY run_no DESC LIMIT ?"
            ),
            (normalized_limit,),
        )
        rows = cursor.fetchall()
    return [
        {
            "run_no": int(row[0]),
            "started_at": str(row[1] or ""),
            "finished_at": str(row[2] or ""),
            "judge_model": str(row[3] or ""),
            "selected_case_count": int(row[4] or 0),
            "pass_rate": float(row[5] or 0.0),
            "avg_score": float(row[6] or 0.0),
            "created_at": str(row[7] or ""),
        }
        for row in rows
    ]


def get_chat_eval_run(run_no: int) -> dict[str, Any] | None:
    """
    특정 차수(run_no)의 Chat Eval 전체 리포트를 조회한다.

    Args:
        run_no: 조회할 실행 차수

    Returns:
        리포트 dict 또는 None
    """
    _ensure_schema()
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT report_json FROM eval_runs WHERE run_no = ?", (int(run_no),))
        row = cursor.fetchone()
    if not row:
        return None
    try:
        loaded = json.loads(str(row[0] or "{}"))
    except json.JSONDecodeError:
        return None
    if not isinstance(loaded, dict):
        return None
    return loaded


def _insert_case_rows(cursor: sqlite3.Cursor, run_no: int, cases: Any) -> None:
    """
    실행 차수에 속한 케이스 결과 행을 저장한다.

    Args:
        cursor: SQLite 커서
        run_no: 실행 차수
        cases: 케이스 결과 목록
    """
    if not isinstance(cases, list):
        return
    for item in cases:
        if not isinstance(item, dict):
            continue
        judge = item.get("judge", {}) if isinstance(item.get("judge"), dict) else {}
        cursor.execute(
            (
                "INSERT INTO eval_case_results "
                "(run_no, case_id, query, pass, score, reason, answer, chat_elapsed_ms, judge_elapsed_ms, requires_current_mail, expectation, error) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)"
            ),
            (
                int(run_no),
                str(item.get("case_id") or ""),
                str(item.get("query") or ""),
                1 if bool(judge.get("pass")) else 0,
                int(judge.get("score") or 0),
                str(judge.get("reason") or ""),
                str(item.get("answer") or ""),
                float(item.get("chat_elapsed_ms") or 0.0),
                float(item.get("judge_elapsed_ms") or 0.0),
                1 if bool(item.get("requires_current_mail")) else 0,
                str(item.get("expectation") or ""),
                str(item.get("error") or ""),
            ),
        )


def _connect() -> sqlite3.Connection:
    """
    Chat Eval SQLite DB 연결을 생성한다.

    Returns:
        sqlite3 연결 객체
    """
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


def _ensure_schema() -> None:
    """
    Chat Eval 이력 저장용 스키마를 보장한다.
    """
    with _connect() as conn:
        cursor = conn.cursor()
        cursor.execute(
            (
                "CREATE TABLE IF NOT EXISTS eval_runs ("
                "run_no INTEGER PRIMARY KEY AUTOINCREMENT, "
                "started_at TEXT NOT NULL, "
                "finished_at TEXT NOT NULL, "
                "chat_url TEXT NOT NULL, "
                "judge_model TEXT NOT NULL, "
                "selected_case_count INTEGER NOT NULL DEFAULT 0, "
                "pass_rate REAL NOT NULL DEFAULT 0, "
                "avg_score REAL NOT NULL DEFAULT 0, "
                "report_json TEXT NOT NULL, "
                "created_at TEXT NOT NULL"
                ")"
            )
        )
        cursor.execute(
            (
                "CREATE TABLE IF NOT EXISTS eval_case_results ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, "
                "run_no INTEGER NOT NULL, "
                "case_id TEXT NOT NULL, "
                "query TEXT NOT NULL, "
                "pass INTEGER NOT NULL, "
                "score INTEGER NOT NULL, "
                "reason TEXT NOT NULL, "
                "answer TEXT NOT NULL, "
                "chat_elapsed_ms REAL NOT NULL DEFAULT 0, "
                "judge_elapsed_ms REAL NOT NULL DEFAULT 0, "
                "requires_current_mail INTEGER NOT NULL DEFAULT 0, "
                "expectation TEXT NOT NULL DEFAULT '', "
                "error TEXT NOT NULL DEFAULT '', "
                "FOREIGN KEY (run_no) REFERENCES eval_runs(run_no) ON DELETE CASCADE"
                ")"
            )
        )
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_eval_runs_created_at ON eval_runs(created_at DESC)")
        cursor.execute("CREATE INDEX IF NOT EXISTS idx_eval_case_results_run_no ON eval_case_results(run_no)")
        conn.commit()
