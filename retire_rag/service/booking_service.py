"""养老服务预约系统 -- SQLite（与 auth 共用 data/app.db）"""

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
    """创建 services 和 bookings 表，首次运行时插入种子数据"""
    conn = _get_conn()
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS services (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                name        TEXT NOT NULL,
                description TEXT,
                price       REAL NOT NULL,
                unit        TEXT NOT NULL,
                icon        TEXT
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS bookings (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id     INTEGER NOT NULL,
                service_id  INTEGER NOT NULL,
                date        TEXT NOT NULL,
                time_slot   TEXT,
                notes       TEXT,
                status      TEXT DEFAULT 'pending',
                created_at  TEXT
            )
        """)
        conn.commit()

        # 种子数据：仅当 services 表为空时插入
        count = conn.execute("SELECT COUNT(*) FROM services").fetchone()[0]
        if count == 0:
            seed = [
                ("助餐",     "提供营养均衡的餐食配送或堂食服务",   25,  "次", "🍽️"),
                ("助洁",     "居室清洁、衣物洗涤、个人卫生协助",   40,  "次", "🧹"),
                ("助医",     "陪同就医、代取药品、健康监测",       80,  "次", "🏥"),
                ("陪护",     "全天候生活陪伴与基本照护",           200, "天", "👨‍⚕️"),
                ("日间照料", "日间托管照护、康复活动、社交娱乐",   100, "天", "☀️"),
            ]
            conn.executemany(
                "INSERT INTO services (name, description, price, unit, icon) VALUES (?, ?, ?, ?, ?)",
                seed,
            )
            conn.commit()
    finally:
        conn.close()


# 前端 service_key → 数据库服务名称映射
SERVICE_KEY_MAP = {
    "meal":    "助餐",
    "clean":   "助洁",
    "medical": "助医",
    "care":    "陪护",
    "daycare": "日间照料",
}


def get_service_by_key(service_key: str) -> dict | None:
    """根据前端字符串 key 查找服务"""
    name = SERVICE_KEY_MAP.get(service_key)
    if not name:
        return None
    conn = _get_conn()
    try:
        row = conn.execute("SELECT * FROM services WHERE name=?", (name,)).fetchone()
        return dict(row) if row else None
    finally:
        conn.close()


def get_all_services() -> list[dict]:
    """返回所有服务项目"""
    conn = _get_conn()
    try:
        rows = conn.execute("SELECT * FROM services ORDER BY id").fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def create_booking(
    user_id: int, service_id: int, date: str, time_slot: str, notes: str = None
) -> dict:
    """创建一条预约记录，返回 {ok, booking_id} 或 {ok: False, error}"""
    conn = _get_conn()
    try:
        service = conn.execute(
            "SELECT id FROM services WHERE id = ?", (service_id,)
        ).fetchone()
        if not service:
            return {"ok": False, "error": "服务不存在"}

        created_at = datetime.now().isoformat()
        cursor = conn.execute(
            "INSERT INTO bookings (user_id, service_id, date, time_slot, notes, created_at) "
            "VALUES (?, ?, ?, ?, ?, ?)",
            (user_id, service_id, date, time_slot, notes, created_at),
        )
        conn.commit()
        return {"ok": True, "booking_id": cursor.lastrowid}
    finally:
        conn.close()


def get_user_bookings(user_id: int, limit: int = 20) -> list[dict]:
    """获取用户预约列表，JOIN services 表附带服务详情"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """
            SELECT b.id, b.user_id, b.service_id, b.date, b.time_slot,
                   b.notes, b.status, b.created_at,
                   s.name        AS service_name,
                   s.description AS service_description,
                   s.price, s.unit, s.icon
            FROM bookings b
            JOIN services s ON b.service_id = s.id
            WHERE b.user_id = ?
            ORDER BY b.created_at DESC
            LIMIT ?
            """,
            (user_id, limit),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()
