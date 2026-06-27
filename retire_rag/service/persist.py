"""
持久化存储模块 — SQLite

替换内存中的问答日志和会话历史。
"""
import sqlite3
import os
import json
from datetime import datetime
from utils.path_tool import get_abs_path
from utils.logger_handler import logger

DB_PATH = get_abs_path("data/app.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表（幂等）"""
    conn = _get_conn()
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS qa_logs (
            id          TEXT PRIMARY KEY,
            timestamp   TEXT NOT NULL,
            query       TEXT NOT NULL,
            answer      TEXT NOT NULL,
            intent      TEXT,
            kb          TEXT,
            sources     TEXT,          -- JSON array
            feedback    INTEGER,       -- 1=有用, -1=无帮助
            comment     TEXT,
            session_id  TEXT
        );

        CREATE TABLE IF NOT EXISTS sessions (
            session_id  TEXT NOT NULL,
            turn        INTEGER NOT NULL,  -- 轮次序号
            query       TEXT NOT NULL,
            answer      TEXT NOT NULL,
            timestamp   TEXT NOT NULL,
            PRIMARY KEY (session_id, turn)
        );

        CREATE TABLE IF NOT EXISTS chunk_config (
            key   TEXT PRIMARY KEY,
            value TEXT NOT NULL
        );
    """)
    conn.commit()
    conn.close()


# ═══════════════════════════════════════════════
# QA 日志
# ═══════════════════════════════════════════════

def save_qa_log(entry: dict):
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO qa_logs
           (id, timestamp, query, answer, intent, kb, sources, feedback, comment, session_id)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            entry["id"],
            entry.get("timestamp", datetime.now().isoformat()),
            entry["query"],
            entry["answer"][:2000],
            entry.get("intent"),
            entry.get("kb"),
            json.dumps(entry.get("sources", []), ensure_ascii=False),
            entry.get("feedback"),
            entry.get("comment"),
            entry.get("session_id"),
        ),
    )
    conn.commit()
    conn.close()


def get_qa_logs(limit: int = 50, kb: str = None) -> list[dict]:
    conn = _get_conn()
    if kb:
        rows = conn.execute(
            "SELECT * FROM qa_logs WHERE kb=? ORDER BY timestamp DESC LIMIT ?",
            (kb, limit),
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM qa_logs ORDER BY timestamp DESC LIMIT ?",
            (limit,),
        ).fetchall()
    conn.close()
    return [_row_to_dict(r) for r in rows]


def update_feedback(log_id: str, score: int, comment: str = ""):
    conn = _get_conn()
    conn.execute(
        "UPDATE qa_logs SET feedback=?, comment=? WHERE id=?",
        (score, comment, log_id),
    )
    conn.commit()
    affected = conn.total_changes
    conn.close()
    return affected > 0


def _row_to_dict(row) -> dict:
    d = dict(row)
    if d.get("sources"):
        try:
            d["sources"] = json.loads(d["sources"])
        except json.JSONDecodeError:
            d["sources"] = []
    return d


# ═══════════════════════════════════════════════
# 会话历史
# ═══════════════════════════════════════════════

def save_session_turn(session_id: str, turn: int, query: str, answer: str):
    conn = _get_conn()
    conn.execute(
        """INSERT OR REPLACE INTO sessions
           (session_id, turn, query, answer, timestamp)
           VALUES (?, ?, ?, ?, ?)""",
        (session_id, turn, query, answer, datetime.now().isoformat()),
    )
    # 保留最近10轮
    conn.execute(
        "DELETE FROM sessions WHERE session_id=? AND turn < ?",
        (session_id, turn - 9),
    )
    conn.commit()
    conn.close()


def get_session_history(session_id: str, limit: int = 10) -> list[dict]:
    conn = _get_conn()
    rows = conn.execute(
        "SELECT query, answer FROM sessions WHERE session_id=? "
        "ORDER BY turn DESC LIMIT ?",
        (session_id, limit),
    ).fetchall()
    conn.close()
    return [{"query": r["query"], "answer": r["answer"]} for r in reversed(rows)]


# ═══════════════════════════════════════════════
# 分片配置
# ═══════════════════════════════════════════════

def get_chunk_config() -> dict:
    conn = _get_conn()
    rows = conn.execute("SELECT key, value FROM chunk_config").fetchall()
    conn.close()
    return {r["key"]: r["value"] for r in rows}


def save_chunk_config(key: str, value: str):
    conn = _get_conn()
    conn.execute(
        "INSERT OR REPLACE INTO chunk_config (key, value) VALUES (?, ?)",
        (key, value),
    )
    conn.commit()
    conn.close()


# 启动初始化
init_db()
logger.info("[Persist]SQLite 持久化初始化完成")
