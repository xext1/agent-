"""
=====================================================================
api/server.py —— FastAPI 接口层（含 SSO 单点登录）
=====================================================================
"""

from contextlib import asynccontextmanager
from pathlib import Path
from typing import Optional

from fastapi import FastAPI, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel, Field

from config import settings
from core.logger import logger
from agent.helpdesk import AgentService
from auth.sso import sso           # SSO 适配器（Mock / 企业微信 / 钉钉...）
from auth.jwt import create_token, decode_token

# ========== 全局对象 ==========

service: AgentService | None = None
STATIC_DIR = Path(__file__).parent / "static"
bearer_scheme = HTTPBearer(auto_error=False)


# ========== 生命周期 ==========

@asynccontextmanager
async def lifespan(app: FastAPI):
    global service
    logger.info("服务启动中，开始初始化 Agent ...")
    service = AgentService()
    logger.info("服务已就绪，监听 %s:%s", settings.HOST, settings.PORT)
    yield
    logger.info("服务关闭")


app = FastAPI(
    title="云帆科技企业服务台 Agent",
    version="1.0.0",
    lifespan=lifespan,
)


# ========== 鉴权依赖 ==========

async def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(bearer_scheme),
):
    """从 JWT 里解析当前登录用户。"""
    if credentials is None:
        raise HTTPException(status_code=401, detail="未登录")
    payload = decode_token(credentials.credentials)
    if payload is None:
        raise HTTPException(status_code=401, detail="token 无效或已过期")
    return {"user_id": payload["sub"], "username": payload["username"]}


# ========== 前端页面路由 ==========

@app.get("/", include_in_schema=False)
def chat_home():
    return FileResponse(str(STATIC_DIR / "index.html"))


@app.get("/login", include_in_schema=False)
def login_page():
    return FileResponse(str(STATIC_DIR / "login.html"))


# ========== 请求格式 ==========

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)


# ========== 接口：健康检查 ==========

@app.get("/health", tags=["运维"])
def health():
    return {"status": "ok"}


# ========== 接口：SSO 登录 ==========

@app.get("/api/v1/auth/sso/mock-users", tags=["认证"])
def sso_mock_users():
    """Mock SSO：给前端下拉框列出模拟员工。真实 SSO 不走这个接口。"""
    if hasattr(sso, "list_mock_users"):
        return {"platform": sso.get_platform_name(), "users": sso.list_mock_users()}
    return {"platform": sso.get_platform_name(), "users": []}


@app.post("/api/v1/auth/sso/exchange", tags=["认证"])
def sso_exchange(body: dict):
    """
    SSO 登录统一入口：
      · Mock 模式：body 里带 mock_user_key（前端选的员工）
      · 真实 SSO：body 里带 code（平台回调回来的授权码）
    """
    code = body.get("code") or body.get("mock_user_key")
    if not code:
        raise HTTPException(status_code=400, detail="缺少 code")

    # 调 SSO 适配器换用户身份
    user = sso.exchange_code(code)

    # 发 JWT
    token = create_token(user["user_id"], user["username"])
    return {
        "token": token,
        "token_type": "bearer",
        "username": user["username"],
        "user_id": user["user_id"],
        "avatar": user.get("avatar", "👤"),
    }


@app.get("/api/v1/auth/me", tags=["认证"])
def me(current_user: dict = Depends(get_current_user)):
    """前端刷新时判断 token 是否还有效。"""
    return current_user


# ========== 接口：对话（需 SSO 登录） ==========

@app.post("/api/v1/chat", tags=["对话"])
def chat(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    session_id = f"user_{current_user['user_id']}"
    try:
        reply = service.chat(session_id, req.message)
        return {"session_id": session_id, "reply": reply}
    except Exception:
        logger.exception("对话失败 user=%s", current_user["username"])
        raise HTTPException(status_code=500, detail="服务暂时不可用")


@app.post("/api/v1/chat/stream", tags=["对话"])
def chat_stream(
    req: ChatRequest,
    current_user: dict = Depends(get_current_user),
):
    session_id = f"user_{current_user['user_id']}"

    async def event_generator():
        try:
            async for text in service.stream_chat(session_id, req.message):
                yield text
        except Exception:
            logger.exception("流式对话失败 user=%s", current_user["username"])
            yield "\n\n（服务开小差了，请稍后重试）"

    return StreamingResponse(event_generator(), media_type="text/plain; charset=utf-8")
