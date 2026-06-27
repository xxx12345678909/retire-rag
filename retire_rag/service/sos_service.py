"""紧急呼叫服务"""
import sqlite3, os
from datetime import datetime
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "app.db"


def _get_conn():
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS sos_alerts (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            username TEXT,
            message TEXT,
            location TEXT DEFAULT '定位获取中...',
            status TEXT DEFAULT 'active',
            created_at TEXT
        )
    """)
    conn.commit()
    conn.close()


def trigger_sos(user_id: int = None, username: str = "", message: str = "紧急求助") -> dict:
    conn = _get_conn()
    created_at = datetime.now().isoformat()
    cursor = conn.execute(
        "INSERT INTO sos_alerts (user_id, username, message, status, created_at) VALUES (?,?,?,?,?)",
        (user_id, username, message, "active", created_at),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM sos_alerts WHERE id=?", (cursor.lastrowid,)).fetchone()
    conn.close()
    return dict(row)


def get_active_alerts() -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT * FROM sos_alerts WHERE status='active' ORDER BY created_at DESC LIMIT 20"
    ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def resolve_alert(alert_id: int) -> bool:
    conn = _get_conn()
    conn.execute("UPDATE sos_alerts SET status='resolved' WHERE id=?", (alert_id,))
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


init_db()
