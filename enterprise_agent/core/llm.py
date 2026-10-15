"""
=====================================================================
core/llm.py —— 大模型工厂
---------------------------------------------------------------------
大白话解释：
  这里负责"造模型对象"，业务代码不用关心密钥、网址这些细节，直接
  调函数拿一个能用的模型。

  企业级亮点：主备故障转移（fallback）
  ------------------------------------
  假如通义千问的服务临时抖动（网络抽风、服务商宕机），Agent 不能直
  接罢工。我们配一个备用模型（豆包），主模型连续失败时 LangChain 会
  自动改用备用模型，用户几乎无感知。这在企业里叫"高可用"。
=====================================================================
"""

from langchain_openai import ChatOpenAI
# ChatOpenAI 是"OpenAI 协议客户端"。通义千问、豆包都兼容 OpenAI 的接口
# 格式，所以同一个类改三个参数（模型名/密钥/网址）就能接入不同厂商。

from langchain_community.embeddings import DashScopeEmbeddings
# DashScope 是阿里云的模型服务平台，DashScopeEmbeddings 负责把文字转向量。

from config import settings
from core.logger import logger


def build_chat_model() -> ChatOpenAI:
    """
    构建对话模型。配了备用模型时，返回"主+备"的组合对象。
    """

    # ---- 主模型：通义千问 ----
    primary = ChatOpenAI(
        model=settings.DASHSCOPE_MODEL,        # 模型名，如 qwen-plus
        api_key=settings.DASHSCOPE_API_KEY,    # 密钥
        base_url=settings.DASHSCOPE_BASE_URL,  # 接口网址
        temperature=0.2,  # 温度=创造力，0~2 之间。企业客服要求稳定，设小一点
        timeout=60,       # 一次请求最多等 60 秒，避免卡死
        max_retries=2,    # SDK 内部自动重试 2 次（针对网络抖动等临时错误）
    )

    # 如果没配豆包密钥，就只返回主模型（不强制每家都用双模型）
    if not settings.DOUBAO_API_KEY:
        logger.info("使用单模型：%s", settings.DASHSCOPE_MODEL)
        return primary

    # ---- 备用模型：豆包 ----
    backup = ChatOpenAI(
        model=settings.DOUBAO_MODEL,
        api_key=settings.DOUBAO_API_KEY,
        base_url=settings.DOUBAO_BASE_URL,
        temperature=0.2,
        timeout=60,
        max_retries=2,
    )

    logger.info(
        "主模型：%s；备用模型：%s（主模型失败自动切换）",
        settings.DASHSCOPE_MODEL,
        settings.DOUBAO_MODEL,
    )

    # with_fallbacks：把备用模型挂在主模型后面。
    # 主模型重试 2 次仍失败时，LangChain 会自动拿备用模型再试一遍。
    return primary.with_fallbacks([backup])


# ---------------- 向量模型（全局只造一次）----------------

# 用一个变量缓存向量模型对象。"单例模式"大白话：整个程序共用一个，
# 避免每次检索知识库都重新初始化、重复建立连接。
_embeddings = None


def get_embeddings() -> DashScopeEmbeddings:
    """获取向量模型（懒加载：第一次调用时才真正创建）。"""
    global _embeddings  # 声明修改的是模块级变量，而不是新建局部变量

    if _embeddings is None:
        _embeddings = DashScopeEmbeddings(
            model=settings.EMBEDDING_MODEL,
            dashscope_api_key=settings.DASHSCOPE_API_KEY,
        )
        logger.info("向量模型初始化完成：%s", settings.EMBEDDING_MODEL)

    return _embeddings
