"""
=====================================================================
tools/knowledge.py —— 知识库工具（RAG）
---------------------------------------------------------------------
大白话解释 RAG（检索增强生成）：
  大模型不知道你们公司的规章制度。所以把公司文档存进向量数据库，
  用户提问时先"检索"出最相关的几段话，连同问题一起交给大模型，让
  它"照着资料回答"，而不是瞎编（瞎编在技术上叫"幻觉"）。

  完整流程：
    文档(.md) → 切小块 → 调向量模型转成数字向量 → 存进 Chroma
    用户提问 → 问题转向量 → 向量库找最相似的几块 → 交给大模型总结

  本文件负责：知识库的自动初始化 + 对外暴露一个检索工具。
=====================================================================
"""

from langchain_core.tools import tool
# @tool 装饰器：把一个普通函数变成"Agent 能调用的工具"。
# 函数的 docstring（三引号说明）会变成工具说明书，大模型靠它判断
# "什么时候该调用这个工具"，所以说明必须写清楚使用场景！

from langchain_community.vectorstores import Chroma
from langchain_community.document_loaders import DirectoryLoader, TextLoader
from langchain_text_splitters import RecursiveCharacterTextSplitter

from config import settings
from core.logger import logger, audit_logger
from core.llm import get_embeddings


# 用变量缓存向量库对象，整个程序共用一个（理由同 llm.py 的单例）
_vectorstore = None


def get_vectorstore() -> Chroma:
    """
    获取向量数据库对象。第一次调用时：
      1. 连接本地 Chroma（不存在会自动创建）
      2. 如果库里是空的，自动读取 data/knowledge/ 下的文档并入库
    """
    global _vectorstore

    if _vectorstore is not None:
        return _vectorstore  # 已经初始化过，直接返回

    # ---- 第 1 步：连接（或创建）Chroma 向量库 ----
    _vectorstore = Chroma(
        collection_name="company_docs",        # 集合名，类似数据库里的"表名"
        embedding_function=get_embeddings(),   # 用哪个向量模型
        persist_directory=str(settings.CHROMA_DIR),  # 数据存到磁盘哪个目录
        # 距离算法用"余弦相似度"：判断两段话意思有多接近
        collection_metadata={"hnsw:space": "cosine"},
    )

    # ---- 第 2 步：检查库里有没有文档，空的话自动导入 ----
    # count() 返回当前向量条数；为 0 说明是第一次运行
    if _vectorstore._collection.count() == 0:
        logger.info("知识库为空，开始导入文档：%s", settings.KNOWLEDGE_DIR)

        # DirectoryLoader：批量加载一个目录下的文件
        # glob="**/*.md" 表示递归找出所有 .md 结尾的文件
        loader = DirectoryLoader(
            path=str(settings.KNOWLEDGE_DIR),
            glob="**/*.md",
            loader_cls=TextLoader,
            loader_kwargs={"encoding": "utf-8"},  # Windows 读中文必须指定编码
        )
        documents = loader.load()  # 得到 Document 列表（每个 Document 有 page_content 和 metadata）

        # ---- 第 3 步：把长文档切成小块 ----
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=settings.RAG_CHUNK_SIZE,      # 每块最多多少字
            chunk_overlap=settings.RAG_CHUNK_OVERLAP,  # 相邻块重叠多少字
        )
        chunks = splitter.split_documents(documents)

        # ---- 第 4 步：切块转向量并入库（add 时自动调用 embedding 模型）----
        _vectorstore.add_documents(chunks)

        logger.info("知识库初始化完成，共导入 %s 个文档片段", len(chunks))

    return _vectorstore


# =====================================================================
# 增量导入：有新文档时只加新的，不动旧数据
# =====================================================================

def _get_indexed_sources(store: Chroma) -> set:
    """
    查向量库里已经导入过哪些源文件（通过 metadata["source"] 记录）。

    返回一个集合，如 {"it_policy.md", "leave_policy.md"}。
    用来跟文件夹里的文件列表对比，找出"还没导入的新文件"。
    """
    # .get() 取出库里所有记录的 metadata（不做相似度计算，只是纯查表）
    all_data = store._collection.get(include=["metadatas"])
    sources = set()
    for meta in all_data.get("metadatas", []):
        if meta and "source" in meta:
            # 只取文件名，跟后面扫文件夹的结果对得上
            sources.add(meta["source"])
    return sources


def add_documents_incremental() -> dict:
    """
    扫描 data/knowledge/ 文件夹，找出"还没导入过的"新文档，只把新文档切块入库。

    返回：{"total_files": 文件夹里共几个文件,
           "new_files": 新导入几个,
           "new_chunks": 新切了多少块,
           "skipped_files": 已存在跳过几个}
    """
    store = get_vectorstore()  # 确保向量库已初始化

    # ---- 第 1 步：扫描文件夹，找出所有 .md 文件 ----
    # rglob("*.md")：递归找出所有 .md 结尾的文件（包括子文件夹里的）
    all_files = list(settings.KNOWLEDGE_DIR.rglob("*.md"))

    if not all_files:
        logger.warning("知识库目录没有 .md 文件：%s", settings.KNOWLEDGE_DIR)
        return {"total_files": 0, "new_files": 0, "new_chunks": 0, "skipped_files": 0}

    # ---- 第 2 步：查库里已有哪些文件，找出"还没导入的新文件" ----
    indexed_sources = _get_indexed_sources(store)  # 已导入的文件名集合

    # 用 TextLoader 逐个加载新文件（只加载未导入的）
    from langchain_core.documents import Document  # Document 类型，用来存"一段文本+来源信息"

    new_documents = []
    skipped_files = []

    for file_path in all_files:
        # file_path.name 是纯文件名，如 "travel_policy.md"
        # 如果这个文件名已经在库里 → 跳过，不重复导入
        if file_path.name in indexed_sources:
            skipped_files.append(file_path.name)
            continue

        # 新文件：用 TextLoader 读取
        loader = TextLoader(str(file_path), encoding="utf-8")
        docs = loader.load()  # 每个文件读成 Document 对象（page_content=全文, metadata.source=文件路径）
        new_documents.extend(docs)
        logger.info("发现新文档：%s", file_path.name)

    # ---- 第 3 步：没有新文件就提前返回 ----
    if not new_documents:
        logger.info("没有新文档需要导入（已全部导入过）")
        return {
            "total_files": len(all_files),
            "new_files": 0,
            "new_chunks": 0,
            "skipped_files": len(skipped_files),
        }

    # ---- 第 4 步：把新文档切块 ----
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=settings.RAG_CHUNK_SIZE,
        chunk_overlap=settings.RAG_CHUNK_OVERLAP,
    )
    new_chunks = splitter.split_documents(new_documents)

    # ---- 第 5 步：新块转向量并入库 ----
    store.add_documents(new_chunks)

    # 审计日志：记录导入了哪些新文件
    audit_logger.info(
        "增量导入完成 新文件=%s 新片段=%s 跳过=%s",
        len(new_documents),
        len(new_chunks),
        len(skipped_files),
    )

    return {
        "total_files": len(all_files),
        "new_files": len(new_documents),
        "new_chunks": len(new_chunks),
        "skipped_files": len(skipped_files),
    }


@tool
def search_knowledge_base(query: str) -> str:
    """
    在公司内部知识库中检索规章制度和办事流程，内容包括：IT 使用规范
    （密码、WiFi、VPN、报修流程）、人事制度（年假、病假、事假）等。

    使用场景：只要员工询问公司制度、办事流程、政策规定，就必须先调用
    本工具查资料，禁止凭自己的记忆编造答案。

    参数：
      query: 员工的问题（或从中提炼出的检索关键词）
    """
    try:
        # 查之前先跑一次增量检查：文件夹里有新文档就自动导入
        add_documents_incremental()
        store = get_vectorstore()

        # 语义检索：问题转向量后，找最相似的前 RAG_TOP_K 个片段
        docs = store.similarity_search(query, k=settings.RAG_TOP_K)

        # 一条都没查到：如实告知，绝不编造
        if not docs:
            return "知识库中没有检索到相关规定，建议为员工创建工单转人工处理。"

        # 把检索结果拼成一段文字返回（Agent 会基于这些内容组织回答）
        result_parts = []
        for index, doc in enumerate(docs, start=1):
            # metadata["source"] 里存着文档的来源文件路径，答复时方便员工核对
            source = doc.metadata.get("source", "未知来源")
            result_parts.append(f"【资料{index}】来源文件：{source}\n{doc.page_content}")

        # 审计：记录谁检索了什么（合规要求，出了问题能追溯）
        audit_logger.info("知识库检索 query=%s 命中=%s 条", query, len(docs))

        return "\n\n".join(result_parts)

    except Exception as error:
        # 工具出错不能把整个 Agent 搞崩：把错误变成"给模型看的提示语"返回，
        # 模型会据此改走"创建工单/稍后再试"的兜底流程
        logger.exception("知识库检索失败")
        return f"知识库检索暂时不可用（原因：{error}），请建议员工稍后重试或创建工单转人工。"
