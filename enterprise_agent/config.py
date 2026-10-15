"""
=====================================================================
config.py —— 全局配置中心
---------------------------------------------------------------------
大白话解释：
  企业项目里，密钥、网址、文件路径这些"可能会变的东西"不能散落在各
  个代码文件里，否则换个环境（开发/测试/生产）要满世界改代码。
  所以统一放到这一个文件里集中管理，其它代码想用就 import 它。
=====================================================================
"""

import os  # Python 自带的库，用来读取系统环境变量
from pathlib import Path  # 面向对象的路径工具，拼路径比手写字符串靠谱

from dotenv import load_dotenv  # 第三方库：把 .env 文件里的内容读进环境变量

# BASE_DIR = 本文件所在的目录（也就是项目根目录 enterprise_agent/）
# __file__ 是 Python 内置变量，代表"当前这个文件的路径"
# resolve() 会把相对路径转成绝对路径；parent 取上一级目录
BASE_DIR = Path(__file__).resolve().parent

# 读取项目根目录下的 .env 文件（如果存在）。
# .env 不存在也不会报错，因为你的系统环境变量里可能已经有密钥了。
load_dotenv(BASE_DIR / ".env")


class Settings:
    """所有配置项都写在这个类里，当作"常量"使用，代码运行时不修改它们。"""

    # ---------------- 主模型：通义千问 ----------------
    # os.getenv("名字", "默认值")：先去环境变量里找，找不到就用默认值
    DASHSCOPE_API_KEY: str = os.getenv("DASHSCOPE_API_KEY", "")
    DASHSCOPE_BASE_URL: str = os.getenv(
        "DASHSCOPE_BASE_URL",
        "https://dashscope.aliyuncs.com/compatible-mode/v1",
    )
    DASHSCOPE_MODEL: str = os.getenv("DASHSCOPE_MODEL", "qwen-plus")

    # ---------------- 备用模型：豆包 ----------------
    DOUBAO_API_KEY: str = os.getenv("DBAPIKEY", "")
    DOUBAO_BASE_URL: str = os.getenv(
        "DOUBAO_BASE_URL", "https://ark.cn-beijing.volces.com/api/v3"
    )
    DOUBAO_MODEL: str = os.getenv("DOUBAO_MODEL", "doubao-seed-evolving")

    # ---------------- 向量模型 ----------------
    EMBEDDING_MODEL: str = os.getenv("EMBEDDING_MODEL", "text-embedding-v3")

    # ---------------- 知识库（RAG）相关 ----------------
    # 原始知识文档（Markdown 文件）放在 data/knowledge/ 目录
    KNOWLEDGE_DIR: Path = BASE_DIR / "data" / "knowledge"
    # 向量数据库持久化目录（程序重启后知识库还在，不用重新建）
    CHROMA_DIR: Path = BASE_DIR / "data" / "chroma_db"
    RAG_TOP_K: int = int(os.getenv("RAG_TOP_K", "3"))  # 每次检索最相关的 3 个片段
    RAG_CHUNK_SIZE: int = 500   # 文档切块：每块最多 500 字
    RAG_CHUNK_OVERLAP: int = 50 # 相邻两块重叠 50 字，避免把一句话拦腰切断

    # ---------------- 会话记忆相关 ----------------
    SESSION_DB: Path = BASE_DIR / "data" / "sessions.db"  # SQLite 数据库文件
    MAX_HISTORY_MESSAGES: int = 20  # 每次对话最多携带最近 20 条历史（防止超出模型长度限制）

    # ---------------- 日志相关 ----------------
    LOG_DIR: Path = BASE_DIR / "logs"
    LOG_LEVEL: str = os.getenv("LOG_LEVEL", "DEBUG")

    # ---------------- HTTP 服务相关 ----------------
    HOST: str = os.getenv("HOST", "0.0.0.0")
    PORT: int = int(os.getenv("PORT", "8000"))

    # ---------------- 认证（JWT） ----------------
    # JWT 签名密钥：生产环境必须改，放 .env 里，别提交到 Git
    JWT_SECRET_KEY: str = os.getenv(
        "JWT_SECRET_KEY",
        "yunfan-enterprise-agent-secret-key-demo-only",
    )


# 全局唯一的配置对象。其它文件统一用：from config import settings
settings = Settings()

# 项目第一次运行时，自动把需要的目录创建出来（parents=True 表示连父目录一起建；
# exist_ok=True 表示目录已存在也不报错）
for _dir in (settings.KNOWLEDGE_DIR, settings.CHROMA_DIR, settings.LOG_DIR):
    _dir.mkdir(parents=True, exist_ok=True)
