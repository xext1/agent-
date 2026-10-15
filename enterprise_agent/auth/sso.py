"""
=====================================================================
auth/sso.py —— SSO（单点登录）适配器框架
---------------------------------------------------------------------
核心思想：把"跟具体 SSO 平台对接"这件事隔离在一个接口后面。
  · 现在用 Mock 实现（演示方便，不用真的扫码）
  · 以后接企业微信 / 钉钉 / AD，只换一个实现类，业务代码一行不动

真实对接企业微信需要：
  1. 在企业微信管理后台创建"自建应用"，拿到 CorpID / AgentID / Secret
  2. 配置回调域名（本地开发需要内网穿透工具如 ngrok）
  3. 后端实现 /api/v1/auth/wechat/callback 处理扫码回调
这里只把骨架写好，真实对接时把 MockSSO 换成 WeChatSSO 即可。
=====================================================================
"""

from abc import ABC, abstractmethod


# ============================================================
# SSO 接口：所有 SSO 实现都必须遵守这个契约
# ============================================================

class SSOProvider(ABC):
    """SSO 平台适配器接口。接任何平台都实现这三个方法。"""

    @abstractmethod
    def get_login_url(self) -> str:
        """返回"让用户跳转去扫码/授权"的那个 URL。"""

    @abstractmethod
    def exchange_code(self, code: str) -> dict:
        """
        用平台回调回来的 code 换取用户身份信息。
        返回 dict：{"user_id": "唯一编号", "username": "显示名", "avatar": "..."}
        """

    @abstractmethod
    def get_platform_name(self) -> str:
        """平台名，给前端显示用，如"企业微信""钉钉""AD域"。"""


# ============================================================
# Mock 实现（演示用，假装扫码成功）
# ============================================================

class MockSSO(SSOProvider):
    """
    本地演示版：点"登录"直接选一个模拟员工，不用真扫码。
    真实环境不会用这个，仅方便开发联调。
    """

    # 假装公司里这些员工
    _MOCK_USERS = {
        "zhang_san":  {"user_id": "E1001", "username": "张三 (IT部)", "avatar": "👨‍💻"},
        "li_si":      {"user_id": "E1002", "username": "李四 (人事部)", "avatar": "👩‍💼"},
        "wang_wu":    {"user_id": "E1003", "username": "王五 (市场部)", "avatar": "🧑‍💼"},
    }

    def get_login_url(self) -> str:
        # Mock 版不跳外部平台，直接在前端弹一个"选员工"的下拉框
        return "/api/v1/auth/sso/mock-users"

    def exchange_code(self, code: str) -> dict:
        # code 就是 key（如 "zhang_san"）
        user = self._MOCK_USERS.get(code, self._MOCK_USERS["zhang_san"])
        return user

    def get_platform_name(self) -> str:
        return "演示模式"

    def list_mock_users(self) -> dict:
        """给前端下拉框用的员工列表。"""
        return self._MOCK_USERS


# ============================================================
# 企业微信实现（骨架，真实对接时填细节）
# ============================================================

class WeChatSSO(SSOProvider):
    """
    真实企业微信扫码登录骨架。
    参考：企业微信"自建应用→网页授权"文档
    https://developer.work.weixin.qq.com/document/path/91770
    """

    def __init__(self, corpid: str, agentid: str, secret: str, redirect_uri: str):
        self.corpid = corpid          # 企业ID
        self.agentid = agentid        # 自建应用AgentID
        self.secret = secret          # 应用Secret
        self.redirect_uri = redirect_uri  # 扫码后企业微信会带着 code 回调到这个地址

    def get_login_url(self) -> str:
        # 拼企业微信扫码授权链接
        # 真实写法：
        # return (
        #     f"https://open.weixin.qq.com/connect/oauth2/authorize"
        #     f"?appid={self.corpid}"
        #     f"&redirect_uri={urlencode(self.redirect_uri)}"
        #     f"&response_type=code"
        #     f"&scope=snsapi_privateinfo"
        #     f"&agentid={self.agentid}"
        #     f"#wechat_redirect"
        # )
        raise NotImplementedError("真实对接企业微信时填写这里")

    def exchange_code(self, code: str) -> dict:
        # 用 code 换 access_token → 再换用户身份
        # 真实写法：
        # 1. 调企业微信API拿 access_token
        # 2. 调 /cgi-bin/user/get?access_token=...&userid=...
        # 3. 返回 {"user_id": userid, "username": name, "avatar": avatar}
        raise NotImplementedError("真实对接企业微信时填写这里")

    def get_platform_name(self) -> str:
        return "企业微信"


# ============================================================
# 单例：项目里统一用这一个 SSO 实例
# ============================================================

def create_sso() -> SSOProvider:
    """
    工厂函数：根据配置决定用哪个 SSO 实现。
    真实项目里从 config 读 SSO_PROVIDER 来决定。
    现在先用 Mock 演示。
    """
    return MockSSO()


sso = create_sso()
