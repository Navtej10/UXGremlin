import os
import json
import time
import sqlite3
from typing import Any

DB_PATH = os.environ.get("DATABASE_PATH", os.path.join(os.path.dirname(__file__), "uxgremlin.db"))


def get_db_connection() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL;")
    conn.execute("PRAGMA foreign_keys = ON;")
    return conn


def init_db() -> None:
    """Initializes the SQLite database schema."""
    conn = get_db_connection()
    try:
        with conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    created_at REAL NOT NULL,
                    url TEXT NOT NULL,
                    task TEXT NOT NULL,
                    persona TEXT NOT NULL,
                    personas TEXT,
                    is_compare INTEGER NOT NULL DEFAULT 0,
                    status TEXT NOT NULL DEFAULT 'running',
                    outcome TEXT,
                    previous_session_id TEXT,
                    report TEXT
                );
            """)
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_created_at ON sessions(created_at);")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_sessions_prev_id ON sessions(previous_session_id);")
    finally:
        conn.close()


def save_session(session_id: str, data: dict[str, Any]) -> None:
    """Inserts or updates session record in SQLite."""
    conn = get_db_connection()
    try:
        url = data.get("url", "")
        task = data.get("task", "")
        persona = data.get("persona", "pro_tester")
        personas = json.dumps(data.get("personas", [persona]))
        is_compare = 1 if data.get("is_compare") else 0
        status = data.get("status", "running")
        outcome = data.get("outcome")
        previous_session_id = data.get("previous_session_id")
        created_at = data.get("created_at", time.time())
        report_json = json.dumps(data["report"]) if data.get("report") else None

        with conn:
            conn.execute("""
                INSERT INTO sessions (
                    id, created_at, url, task, persona, personas, is_compare,
                    status, outcome, previous_session_id, report
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    status = excluded.status,
                    outcome = excluded.outcome,
                    report = COALESCE(excluded.report, sessions.report);
            """, (
                session_id, created_at, url, task, persona, personas, is_compare,
                status, outcome, previous_session_id, report_json
            ))
    finally:
        conn.close()


def save_report(session_id: str, report: dict[str, Any]) -> None:
    """Persists a final report for a session in SQLite."""
    conn = get_db_connection()
    try:
        outcome = report.get("outcome", "completed")
        status = "completed"
        report_json = json.dumps(report)
        with conn:
            conn.execute("""
                UPDATE sessions
                SET status = ?, outcome = ?, report = ?
                WHERE id = ?;
            """, (status, outcome, report_json, session_id))
    finally:
        conn.close()


def get_session(session_id: str) -> dict[str, Any] | None:
    """Retrieves session metadata from SQLite."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT * FROM sessions WHERE id = ?;", (session_id,))
        row = cur.fetchone()
        if not row:
            return None

        data = dict(row)
        if data.get("personas"):
            try:
                data["personas"] = json.loads(data["personas"])
            except Exception:
                data["personas"] = [data["persona"]]
        if data.get("report"):
            try:
                data["report"] = json.loads(data["report"])
            except Exception:
                pass
        data["is_compare"] = bool(data.get("is_compare"))
        return data
    finally:
        conn.close()


def get_report(session_id: str) -> dict[str, Any] | None:
    """Retrieves report dictionary from SQLite for a session."""
    conn = get_db_connection()
    try:
        cur = conn.cursor()
        cur.execute("SELECT report FROM sessions WHERE id = ?;", (session_id,))
        row = cur.fetchone()
        if not row or not row["report"]:
            return None
        return json.loads(row["report"])
    except Exception:
        return None
    finally:
        conn.close()


def compute_report_delta(prev_report: dict[str, Any], new_report: dict[str, Any]) -> dict[str, Any]:
    """
    Computes delta between previous report and new report:
    score difference, outcome change, resolved findings, new findings, persistent findings.
    """
    def _extract_score(rep: dict[str, Any]) -> int:
        score_val = rep.get("score")
        if isinstance(score_val, dict):
            return int(score_val.get("total", 0))
        if isinstance(score_val, (int, float)):
            return int(score_val)
        return 0

    prev_score = _extract_score(prev_report)
    new_score = _extract_score(new_report)
    score_delta = new_score - prev_score  # negative means friction decreased (improvement)

    prev_findings = prev_report.get("findings", [])
    new_findings = new_report.get("findings", [])

    def _normalize_title(t: str) -> str:
        return t.strip().lower()

    prev_map = {_normalize_title(f.get("title", "")): f for f in prev_findings if f.get("title")}
    new_map = {_normalize_title(f.get("title", "")): f for f in new_findings if f.get("title")}

    resolved = [f for key, f in prev_map.items() if key not in new_map]
    new = [f for key, f in new_map.items() if key not in prev_map]
    persistent = [new_map[key] for key in prev_map if key in new_map]

    return {
        "previous_session_id": prev_report.get("session_id"),
        "previous_score": prev_score,
        "new_score": new_score,
        "score_delta": score_delta,
        "previous_outcome": prev_report.get("outcome", "unknown"),
        "new_outcome": new_report.get("outcome", "unknown"),
        "resolved_findings": resolved,
        "new_findings": new,
        "persistent_findings": persistent,
    }
