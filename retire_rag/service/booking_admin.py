"""预约管理 API（管理员专用）"""
from datetime import datetime
from service.booking_service import _get_conn


def get_all_bookings(limit: int = 50) -> list[dict]:
    """管理员：获取所有预约"""
    conn = _get_conn()
    try:
        rows = conn.execute(
            """SELECT b.*, s.name AS service_name, s.price, s.unit,
                      u.username AS user_name
               FROM bookings b
               JOIN services s ON b.service_id = s.id
               LEFT JOIN users u ON b.user_id = u.id
               ORDER BY b.created_at DESC LIMIT ?""",
            (limit,),
        ).fetchall()
        return [dict(r) for r in rows]
    finally:
        conn.close()


def update_booking_status(booking_id: int, status: str) -> bool:
    """Update booking status (confirmed / cancelled)"""
    conn = _get_conn()
    try:
        conn.execute("UPDATE bookings SET status=? WHERE id=?", (status, booking_id))
        conn.commit()
        return conn.total_changes > 0
    finally:
        conn.close()
