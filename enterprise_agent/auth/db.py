"""
=====================================================================
auth/db.py —— 用户表（SQLite）
---------------------------------------------------------------------
在已有的 sessions.db 里加一张 users 表，存用户信息 + 密码哈希。
密码用 SHA256 + 随机盐哈希，不用 bcrypt 避免版本冲突。
=====================================================================
"""

import sqlite3
import hashlib
import secrets    # Python 自带的随机数库，用来生成盐
from pathlib import Path

from config import settings

# 跟 session.py 共用同一个数据库文件 sessions.db
_db_path = str(settings.SESSION_DB)

_CREATE_USERS_TABLE = """
CREATE TABLE IF NOT EXISTS users (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    username     TEXT UNIQUE NOT NULL,
    password_hash TEXT NOT NULL,
    salt         TEXT NOT NULL,            -- 每个用户一个随机盐
    created_at   REAL NOT NULL
);
"""


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(_db_path)
    conn.executescript(_CREATE_USERS_TABLE)
    return conn


# ============================================
# 密码工具（SHA256 + 随机盐）
# ============================================
# 为什么要加盐：相同密码（如 "123456"）不同用户哈希也不同，防彩虹表攻击

def hash_password(plain_password: str) -> tuple[str, str]:
    """把明文密码转成 (salt, hash)，存数据库用。"""
    salt = secrets.token_hex(16)                          # 32 位随机盐
    salted = (salt + plain_password).encode("utf-8")
    h = hashlib.sha256(salted).hexdigest()               # SHA256 输出 64 位十六进制字符串
    return (salt, h)


def verify_password(plain_password: str, salt: str, password_hash: str) -> bool:
    """把用户登录时输入的明文 + 数据库里的盐，算一次哈希，跟存的对比。"""
    salted = (salt + plain_password).encode("utf-8")
    h = hashlib.sha256(salted).hexdigest()
    return h == password_hash


# ============================================
# 用户增查
# ============================================

def create_user(username: str, password: str) -> bool:
    """注册新用户。成功返回 True，用户名已存在返回 False。"""
    salt, password_hash = hash_password(password)
    with _connect() as conn:
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, salt, created_at) "
                "VALUES (?, ?, ?, ?)",
                (username, password_hash, salt, __import__("time").time()),
            )
            return True
        except sqlite3.IntegrityError:
            return False


def get_user(username: str):
    """按用户名查用户。找到返回字典，找不到返回 None。"""
    with _connect() as conn:
        row = conn.execute(
            "SELECT id, username, password_hash, salt FROM users WHERE username = ?",
            (username,),
        ).fetchone()

    if row is None:
        return None
    return {"id": row[0], "username": row[1], "password_hash": row[2], "salt": row[3]}


def authenticate(username: str, password: str):
    """登录验密。成功返回用户字典，失败返回 None。"""
    user = get_user(username)
    if user is None:
        return None
    if not verify_password(password, user["salt"], user["password_hash"]):
        return None
    return user


# ============================================
# 首次启动时创建一个默认账号（演示用）
# ============================================

def ensure_default_user():
    if get_user("admin") is None:
        create_user("admin", "admin123")
