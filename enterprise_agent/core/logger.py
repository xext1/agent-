"""
=====================================================================
core/logger.py —— 统一日志系统
---------------------------------------------------------------------
大白话解释：
  print 只能在屏幕上看一眼，程序关了就没了。企业项目排查问题靠"日志"：
  把程序每一步干了什么、报错信息写到文件里，永久保存、随时可查。

  本项目拆成两类日志：
    1. logger（运行日志）：程序启动、收到消息、报错……给开发/运维看
    2. audit_logger（审计日志）：谁在什么时候让 Agent 调了什么工具、
       创建了什么工单。这类记录企业里要单独存，方便合规追溯。
=====================================================================
"""

import sys  # 用于获取标准输出（控制台）
import logging  # Python 自带的日志库
from logging.handlers import TimedRotatingFileHandler  # "按天切分"日志文件的处理器

from config import settings  # 导入全局配置（日志目录、日志级别）


def setup_logger(name: str, log_file: str, level: str = None) -> logging.Logger:
    """
    创建并配置一个日志记录器。

    参数解释：
      name     : 日志记录器的名字，不同名字互相独立
      log_file : 日志写到哪个文件
      level    : 日志级别（DEBUG 最详细，INFO 常规，WARNING 警告，ERROR 错误）
    """

    # 先按名字取日志器；同名多次取到的是同一个对象
    logger = logging.getLogger(name)

    # 设置最低记录级别（没传就用配置文件里的级别）
    logger.setLevel(level or settings.LOG_LEVEL)

    # 清空旧的处理器：防止重复初始化时同一条日志打印两遍
    logger.handlers.clear()

    # 统一日志格式：时间 | 级别 | 日志器名字 | 具体内容
    # 例如：2026-10-08 14:30:01 | INFO    | app | 收到消息 ...
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-7s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    # ---- 处理器 1：写文件，每天零点切一个新文件，保留最近 30 天 ----
    # 旧文件会自动改名带日期后缀，30 天前的自动删除
    file_handler = TimedRotatingFileHandler(
        filename=log_file,
        when="midnight",       # 切分时机：每天半夜
        backupCount=30,        # 最多保留 30 个历史文件
        encoding="utf-8",      # Windows 下不写会乱码
    )
    file_handler.setFormatter(formatter)

    # ---- 处理器 2：同时输出到控制台，方便开发时实时观察 ----
    console_handler = logging.StreamHandler(stream=sys.stdout)
    console_handler.setFormatter(formatter)

    # 把两个处理器装到日志器上：日志会"同时"进文件和控制台
    logger.addHandler(file_handler)
    logger.addHandler(console_handler)

    # propagate=False：不让日志再往上级日志器冒泡，避免重复打印
    logger.propagate = False

    return logger


# 全局日志对象，其它代码直接 import 使用
# 运行日志 → logs/app.log
logger = setup_logger("app", settings.LOG_DIR / "app.log")

# 审计日志 → logs/audit.log（与运行日志分开，权限和保存周期可以单独管理）
audit_logger = setup_logger("audit", settings.LOG_DIR / "audit.log")
