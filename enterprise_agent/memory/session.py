"""
=====================================================================
memory/session.py —— 会话记忆（SQLite 持久化）
---------------------------------------------------------------------
大白话解释：
  你在 Custom Function.py 里用的 InMemoryChatMessageHistory 有个致命
  问题：存在内存里，程序一重启，员工跟 Agent 的聊天记录全没了。

  企业里要"持久化"：把对话存进 SQLite 数据库文件（Python 自带，
  不用装数据库服务），重启后历史还在。

  另外做"滑动窗口"：一个员工聊了几百轮时，不可能把全部历史都塞给
  模型（有长度上限，还费钱）。只取最近 20 条，老的记录在库里留档
  但不参与对话。
=====================================================================
"""

import sqlite3  # Python 自带的轻量数据库
import time
from pathlib import Path

from config import settings
from core.logger import logger


# 建表语句。IF NOT EXISTS：表已存在不会报错，程序可以反复启动
_SCHEMA = """
CREATE TABLE IF NOT EXISTS messages (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,  -- 自增主键，同时保证消息先后顺序
    session_id TEXT    NOT NULL,                   -- 会话编号：区分不同员工/不同对话
    role       TEXT    NOT NULL,                   -- 角色：user（员工）/ assistant（Agent）
    content    TEXT    NOT NULL,                   -- 消息正文
    created_at REAL    NOT NULL                    -- 发送时间（时间戳：秒数）
);
"""


class SessionMemory:
    """会话记忆的增、取、删，所有方法都直接操作 SQLite 文件。"""

    def __init__(self, db_path: Path = None):
        self.db_path = str(db_path or settings.SESSION_DB)

        # 确保 data/ 目录存在（第一次运行时数据库文件的父目录可能还没有）
        Path(self.db_path).parent.mkdir(parents=True, exist_ok=True)

        # 建表（with 语句会自动提交事务、自动关闭连接）
        with self._connect() as conn:
            conn.executescript(_SCHEMA)

    def _connect(self) -> sqlite3.Connection:
        """建立一个数据库连接。每次操作新开一个，用完即关，简单可靠。"""
        return sqlite3.connect(self.db_path)

    def append(self, session_id: str, role: str, content: str) -> None:
        """往会话末尾追加一条消息。"""
        with self._connect() as conn:
            conn.execute(
                "INSERT INTO messages (session_id, role, content, created_at) "
                "VALUES (?, ?, ?, ?)",
                (session_id, role, content, time.time()),
            )

    def recent_messages(self, session_id: str, limit: int = None):
        """
        取最近 N 条历史，按"时间正序"返回（老的在前，新的在后）。

        思路（嵌套查询）：
          内层：按 id 倒序取最近 N 条（拿到的是新→老）
          外层：再按 id 正序排回来（老→新），这样喂给模型时对话顺序才对
        """
        limit = limit or settings.MAX_HISTORY_MESSAGES

        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT role, content FROM (
                    SELECT id, role, content
                    FROM messages
                    WHERE session_id = ?
                    ORDER BY id DESC
                    LIMIT ?
                ) ORDER BY id ASC
                """,
                (session_id, limit),
            ).fetchall()

        # 转成字典列表，方便上层组装消息
        return [{"role": role, "content": content} for role, content in rows]

    def clear(self, session_id: str) -> None:
        """清空某个会话的全部历史（员工主动要求"重新开始"时用）。"""
        with self._connect() as conn:
            conn.execute("DELETE FROM messages WHERE session_id = ?", (session_id,))
        logger.info("会话记忆已清空 session=%s", session_id)
