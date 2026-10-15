"""
=====================================================================
tools/ticket_system.py —— 工单系统工具
---------------------------------------------------------------------
模拟企业内部工单系统（真实项目里这里是调用公司 OA/ITSM 系统的
HTTP 接口，业务逻辑完全一样）。

企业级亮点：
  1. 自动重试：调用企业内部接口可能超时，失败后自动重试 3 次
  2. 写操作二次确认：创建工单是"会留痕、要派人干活"的正式操作，
     不能让大模型一句话就提交。先建"草稿"，员工确认后才正式生效
  3. 全程审计日志：查询和创建都记录到 audit.log
  4. 异常兜底：系统挂了返回友好提示，不让错误堆栈暴露给员工
=====================================================================
"""

import time
import uuid
from datetime import datetime

from langchain_core.tools import tool

from core.logger import logger, audit_logger


# =====================================================================
# 下面是"模拟的企业工单数据库"。真实项目中应替换成 requests 调用
# 公司内部系统（如 ServiceNow、Jira、自研 OA）。
# =====================================================================

# 已正式提交的工单：工单号 -> 工单详情
_TICKETS = {
    "TK-1001": {
        "title": "电脑无法开机",
        "description": "按电源键无反应，已尝试拔电源重插",
        "priority": "高",
        "status": "处理中",
        "assignee": "IT-王工",
        "created_at": "2026-10-08 09:00",
    },
}

# 待确认的工单草稿池：确认码 -> 草稿内容
# （员工确认提交前，工单只躺在这里，不会进入正式系统）
_PENDING_DRAFTS = {}


def _call_with_retry(api_func, *args, **kwargs):
    """
    模拟"调用企业内部接口"的通用外壳：失败自动重试，最多 3 次。

    大白话：网络接口偶尔超时是常事，失败一次就报错太脆弱。重试 3 次，
    每次多等一会儿（0.5 秒、1 秒、1.5 秒），大概率能扛过临时抖动。
    """
    last_error = None

    for attempt in range(1, 4):  # attempt 依次为 1、2、3
        try:
            return api_func(*args, **kwargs)  # 成功就立刻返回
        except Exception as error:
            last_error = error
            logger.warning("工单系统第 %s 次调用失败：%s", attempt, error)
            time.sleep(0.5 * attempt)  # 退避等待，别疯狂重试把服务打挂

    # 3 次都失败，把最后一次的错误抛给上层兜底
    raise last_error


# ============================== 工具 1 ==============================

@tool
def query_ticket(ticket_id: str) -> str:
    """
    根据工单号查询工单的处理状态、处理人和详情。

    使用场景：员工询问"我的工单怎么样了 / 工单进度 / 谁在处理"时调用。
    参数：
      ticket_id: 工单号，格式形如 TK-1001
    """

    def _do_query():
        # 去掉员工误输入的空格，并统一转大写（tk-1001 → TK-1001）
        normalized = ticket_id.strip().upper()
        ticket = _TICKETS.get(normalized)

        if ticket is None:
            return f"没有查到工单 {normalized}，请员工核对工单号是否正确（格式如 TK-1001）。"

        return (
            f"工单 {normalized} 详情："
            f"标题「{ticket['title']}」；"
            f"状态：{ticket['status']}；"
            f"优先级：{ticket['priority']}；"
            f"处理人：{ticket['assignee']}；"
            f"创建时间：{ticket['created_at']}。"
        )

    try:
        result = _call_with_retry(_do_query)
        audit_logger.info("查询工单 ticket_id=%s 结果=%s", ticket_id, result[:80])
        return result
    except Exception as error:
        logger.exception("查询工单失败 ticket_id=%s", ticket_id)
        # 不把技术报错甩给员工，返回人类能看懂的话
        return f"工单系统暂时不可用（{error}），请员工稍后再试。"


# ============================== 工具 2 ==============================

@tool
def create_ticket(title: str, description: str, priority: str = "普通") -> str:
    """
    创建工单"草稿"（注意：此时还没有正式提交！）。

    使用场景：知识库无法直接解决员工的问题（如设备故障、需要专人处理的
    诉求）时，先调用本工具生成草稿，把内容念给员工确认。
    参数：
      title: 工单标题，一句话概括问题
      description: 问题详情（现象、已尝试的办法等）
      priority: 优先级，只能填 高 / 普通 / 低，默认普通
    """

    # 校验优先级：模型万一传了奇怪的值，统一归为"普通"
    if priority not in ("高", "普通", "低"):
        priority = "普通"

    # 生成一次性确认码（用 uuid 随机数前 6 位，防止员工自己猜到）
    confirm_code = "C" + uuid.uuid4().hex[:6].upper()

    # 草稿先放进待确认池，不进正式工单表
    _PENDING_DRAFTS[confirm_code] = {
        "title": title,
        "description": description,
        "priority": priority,
    }

    audit_logger.info("生成工单草稿 code=%s title=%s", confirm_code, title)

    # 返回内容是"给大模型看的操作指引"：明确告诉它下一步必须先征得
    # 员工确认，再调用 confirm_ticket —— 这就是"人机协同"的写法
    return (
        f"工单草稿已生成（尚未提交）：\n"
        f"标题：{title}\n优先级：{priority}\n详情：{description}\n"
        f"确认码：{confirm_code}\n"
        f"操作要求：请把以上内容复述给员工确认。员工说「确认/没问题」后，"
        f"调用 confirm_ticket 工具并传入确认码正式提交；员工要修改，"
        f"则重新收集信息并创建草稿。"
    )


# ============================== 工具 3 ==============================

@tool
def confirm_ticket(confirm_code: str) -> str:
    """
    根据确认码把工单草稿正式提交进工单系统。

    使用场景：仅在员工已经明确确认工单内容后调用。
    参数：
      confirm_code: create_ticket 返回的确认码
    """

    # pop：取出草稿并从待确认池删除（确认码只能用一次，防止重复提交）
    draft = _PENDING_DRAFTS.pop(confirm_code.strip().upper(), None)

    if draft is None:
        return f"确认码 {confirm_code} 无效或已使用，请重新创建工单草稿。"

    # 生成正式工单号：TK-1002、TK-1003……（在已有数量上递增）
    ticket_id = f"TK-{1000 + len(_TICKETS) + 1}"

    # 写入正式工单表
    _TICKETS[ticket_id] = {
        **draft,  # 把草稿里的 title/description/priority 展开进来
        "status": "待受理",
        "assignee": "待分配",
        "created_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
    }

    audit_logger.info("工单正式提交 ticket_id=%s title=%s", ticket_id, draft["title"])

    return (
        f"工单已正式提交！工单号：{ticket_id}，状态：待受理。"
        f"处理人将在 1 个工作日内联系员工。请把工单号明确告知员工并提醒保存。"
    )
