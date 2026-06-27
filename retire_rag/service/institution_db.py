"""
养老机构数据库 — SQLite

存储机构信息，支持按区域/护理等级/价格筛选推荐。
首次运行时自动建表并插入示例数据。
"""
import sqlite3
import os
from utils.path_tool import get_abs_path
from utils.logger_handler import logger

DB_PATH = get_abs_path("data/institutions.db")


def _get_conn() -> sqlite3.Connection:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    """建表 + 插入示例数据（幂等）"""
    conn = _get_conn()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS institutions (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            name        TEXT NOT NULL,
            district    TEXT NOT NULL,       -- 区域：朝阳区/海淀区/...
            type        TEXT NOT NULL,       -- 类型：养老院/护理院/社区照料中心
            price_min   INTEGER NOT NULL,    -- 最低月费（元）
            price_max   INTEGER NOT NULL,    -- 最高月费（元）
            care_levels TEXT NOT NULL,       -- 护理等级，逗号分隔：自理,轻度失能,中度失能,重度失能
            beds_total  INTEGER DEFAULT 0,
            beds_avail  INTEGER DEFAULT 0,
            address     TEXT,
            contact     TEXT,
            description TEXT
        )
    """)

    # 检查是否已有数据
    count = conn.execute("SELECT COUNT(*) FROM institutions").fetchone()[0]
    if count > 0:
        conn.close()
        return

    # 插入示例机构数据
    sample = [
        ("朝阳区康怡养老院", "朝阳区", "养老院", 3000, 5000,
         "自理,轻度失能,中度失能", 120, 8,
         "朝阳区建国路88号", "010-65001234",
         "毗邻朝阳公园，环境优美，配备专业医护团队"),
        ("海淀区颐和护理院", "海淀区", "护理院", 4500, 8000,
         "轻度失能,中度失能,重度失能", 80, 5,
         "海淀区颐和园路15号", "010-62881234",
         "专注失能老人照护，24小时医生值班，康复理疗设施齐全"),
        ("西城区金色年华养老社区", "西城区", "养老院", 5000, 10000,
         "自理,轻度失能", 200, 20,
         "西城区金融街12号", "010-66001234",
         "高端养老社区，独立公寓户型，文娱活动丰富"),
        ("丰台区安馨养老照料中心", "丰台区", "社区照料中心", 2000, 3500,
         "自理,轻度失能,中度失能,重度失能", 60, 3,
         "丰台区方庄路6号", "010-87651234",
         "社区嵌入式照料，离家近探视方便，支持短期托管"),
        ("东城区仁爱护理院", "东城区", "护理院", 4000, 7000,
         "中度失能,重度失能", 50, 2,
         "东城区东直门外大街30号", "010-84561234",
         "专业失能失智照护，一对一护理方案，家属可随时探望"),
        ("通州区阳光家园养老院", "通州区", "养老院", 2500, 4000,
         "自理,轻度失能,中度失能", 150, 15,
         "通州区梨园镇云景东路", "010-81561234",
         "环境清幽，价格适中，适合郊区养老需求"),
    ]

    conn.executemany(
        """INSERT INTO institutions
           (name, district, type, price_min, price_max, care_levels,
            beds_total, beds_avail, address, contact, description)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        sample,
    )
    conn.commit()
    conn.close()
    logger.info(f"[InstitutionDB]初始化完成：{len(sample)} 家示例机构")


def search_institutions(
    district: str = None,
    care_level: str = None,
    price_max: int = None,
    limit: int = 5,
) -> list[dict]:
    """按条件筛选机构

    Args:
        district: 区域，如"朝阳区"
        care_level: 护理等级，如"中度失能"
        price_max: 月费上限
        limit: 返回条数上限

    Returns:
        匹配的机构列表
    """
    conn = _get_conn()
    sql = "SELECT * FROM institutions WHERE 1=1"
    params = []

    if district:
        sql += " AND district LIKE ?"
        params.append(f"%{district}%")
    if care_level:
        sql += " AND care_levels LIKE ?"
        params.append(f"%{care_level}%")
    if price_max is not None:
        sql += " AND price_min <= ?"
        params.append(price_max)

    sql += " ORDER BY beds_avail DESC LIMIT ?"
    params.append(limit)

    rows = conn.execute(sql, params).fetchall()
    conn.close()

    return [dict(r) for r in rows]


def get_all_districts() -> list[str]:
    """获取所有区域列表"""
    conn = _get_conn()
    rows = conn.execute(
        "SELECT DISTINCT district FROM institutions ORDER BY district"
    ).fetchall()
    conn.close()
    return [r[0] for r in rows]


# 启动时初始化
init_db()
