import sqlite3, hashlib, datetime

conn = sqlite3.connect("data/app.db")
pw = hashlib.sha256("admin123".encode()).hexdigest()
try:
    conn.execute(
        "INSERT INTO users (username, password_hash, role, created_at) VALUES (?,?,?,?)",
        ("admin", pw, "admin", datetime.datetime.now().isoformat()),
    )
    conn.commit()
    print("管理员创建成功: admin / admin123")
except Exception as e:
    print(f"已存在或失败: {e}")
conn.close()
