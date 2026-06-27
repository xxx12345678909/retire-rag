"""用户家庭档案服务 — 纯标准库实现"""

import sqlite3
from datetime import datetime
from pathlib import Path

DB_DIR = Path(__file__).resolve().parent.parent / "data"
DB_PATH = DB_DIR / "app.db"


def _get_conn() -> sqlite3.Connection:
    DB_DIR.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    return conn


def init_db():
    """创建 family_members 表（如果不存在）"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS family_members (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                name TEXT NOT NULL,
                id_card TEXT NOT NULL,
                relation TEXT NOT NULL,
                notes TEXT DEFAULT '',
                created_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def bind_family(user_id: int, name: str, id_card: str, relation: str, notes: str = "") -> dict:
    """绑定家庭成员"""
    conn = _get_conn()
    try:
        created_at = datetime.now().isoformat()
        cursor = conn.execute(
            "INSERT INTO family_members (user_id, name, id_card, relation, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, name, id_card, relation, notes, created_at),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM family_members WHERE id = ?", (cursor.lastrowid,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


def get_family(user_id: int) -> list[dict]:
    """获取用户所有家庭成员"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            "SELECT * FROM family_members WHERE user_id = ? ORDER BY created_at DESC",
            (user_id,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
