"""用户认证服务 — 纯标准库实现"""

import sqlite3
import hashlib
import base64
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
    """创建 users 表（如果不存在）"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT DEFAULT 'user',
                phone TEXT,
                created_at TEXT
            )
        """)
        conn.commit()
    finally:
        conn.close()


def register(username: str, password: str, phone: str = None) -> dict:
    """注册新用户"""
    conn = _get_conn()
    try:
        existing = conn.execute(
            "SELECT id FROM users WHERE username = ?", (username,)
        ).fetchone()
        if existing:
            return {"ok": False, "error": "用户名已存在"}

        password_hash = hashlib.sha256(password.encode()).hexdigest()
        created_at = datetime.now().isoformat()

        cursor = conn.execute(
            "INSERT INTO users (username, password_hash, phone, created_at) VALUES (?, ?, ?, ?)",
            (username, password_hash, phone, created_at),
        )
        conn.commit()
        return {"ok": True, "user_id": cursor.lastrowid}
    finally:
        conn.close()


def login(username: str, password: str) -> dict:
    """用户登录"""
    conn = _get_conn()
    try:
        row = conn.execute(
            "SELECT id, username, password_hash, role FROM users WHERE username = ?",
            (username,),
        ).fetchone()

        if row is None:
            return {"ok": False}

        expected = hashlib.sha256(password.encode()).hexdigest()
        if row["password_hash"] != expected:
            return {"ok": False}

        timestamp = datetime.now().isoformat()
        raw = f"{row['id']}:{row['username']}:{row['role']}:{timestamp}"
        token = base64.b64encode(raw.encode()).decode()

        return {"ok": True, "token": token, "role": row["role"], "username": row["username"]}
    finally:
        conn.close()


def get_user_by_token(token: str) -> dict | None:
    """根据 token 获取用户信息"""
    try:
        raw = base64.b64decode(token.encode()).decode()
        parts = raw.split(":", 3)
        if len(parts) != 4:
            return None
        user_id, username, role, _timestamp = parts

        conn = _get_conn()
        try:
            row = conn.execute(
                "SELECT id, username, role, phone FROM users WHERE id = ? AND username = ?",
                (int(user_id), username),
            ).fetchone()

            if row is None:
                return None

            return {"id": row["id"], "username": row["username"], "role": row["role"], "phone": row["phone"]}
        finally:
            conn.close()
    except Exception:
        return None
