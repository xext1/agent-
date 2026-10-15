"""
=====================================================================
main.py —— 命令行演示入口（学习调试时最简单的玩法，不用启动网页）
---------------------------------------------------------------------
运行方法：
    1. 先进入项目目录：
         cd "C:/Users/汪学涛/Desktop/新建文件夹 (4)/enterprise_agent"
    2. 运行：
         python main.py
    3. 直接打字跟小帆对话，输入 exit 退出，输入 clear 清空记忆

可以试试这些问题（覆盖全部工具）：
    · 公司的密码有什么要求？              → 走知识库
    · 我入职 3 年了，年假有几天？          → 走知识库
    · 帮我查查 TK-1001 工单               → 查工单工具
    · 我电脑蓝屏了                        → 创建草稿 → 你说"确认" → 正式提交
    · 我刚才说的什么问题？                → 验证它是否记得上下文
=====================================================================
"""

from agent.helpdesk import AgentService


def main():
    # 打印欢迎横幅
    print("=" * 64)
    print(" 云帆科技企业服务台（命令行版）")
    print(" 输入问题开始对话 | exit 退出 | clear 清空记忆")
    print("=" * 64)

    # 初始化 Agent（第一次运行会自动建知识库，需要十几秒，耐心等）
    print("正在装载知识库，请稍候 ...")
    service = AgentService()

    # 命令行里写死一个会话号；真实场景它对应员工工号
    session_id = "cli_user"

    # 无限循环：员工问一句、Agent 答一句，直到输入 exit
    while True:
        try:
            user_text = input("\n我：").strip()
        except (EOFError, KeyboardInterrupt):
            # Ctrl+C / Ctrl+Z 时体面退出，不打印一堆报错
            break

        if not user_text:
            continue  # 空消息不处理，重新等输入

        if user_text.lower() == "exit":
            break

        if user_text.lower() == "clear":
            service.memory.clear(session_id)
            print("（对话记忆已清空，我们重新开始）")
            continue

        # 调用 Agent 拿到回答（这里面会自动检索知识库/调工具）
        reply = service.chat(session_id, user_text)
        print("\n小帆：" + reply)

    print("\n再见！")


# Python 惯例：直接运行本文件时才执行 main()，被 import 时不执行
if __name__ == "__main__":
    main()
