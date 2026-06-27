"""健康档案服务 — 纯标准库实现"""

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
    """创建 health_profiles 表（如果不存在）"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS health_profiles (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER UNIQUE NOT NULL,
                elder_name TEXT NOT NULL,
                age INTEGER NOT NULL,
                chronic_diseases TEXT DEFAULT '',
                medications TEXT DEFAULT '',
                notes TEXT DEFAULT '',
                updated_at TEXT NOT NULL
            )
        """)
        conn.commit()
    finally:
        conn.close()


def get_profile(user_id: int) -> dict | None:
    """获取用户健康档案"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT * FROM health_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def upsert_profile(
    user_id: int,
    elder_name: str,
    age: int,
    chronic_diseases: str = "",
    medications: str = "",
    notes: str = "",
) -> dict:
    """创建或更新健康档案"""
    conn = _get_conn()
    try:
        updated_at = datetime.now().isoformat()
        conn.execute(
            "INSERT INTO health_profiles (user_id, elder_name, age, chronic_diseases, medications, notes, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(user_id) DO UPDATE SET "
            "elder_name=excluded.elder_name, age=excluded.age, "
            "chronic_diseases=excluded.chronic_diseases, medications=excluded.medications, "
            "notes=excluded.notes, updated_at=excluded.updated_at",
            (user_id, elder_name, age, chronic_diseases, medications, notes, updated_at),
        )
        conn.commit()
        row = conn.execute(
            "SELECT * FROM health_profiles WHERE user_id = ?", (user_id,)
        ).fetchone()
        return dict(row)
    finally:
        conn.close()


init_db()
