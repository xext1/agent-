"""
=====================================================================
auth/jwt.py —— JWT 令牌工具
---------------------------------------------------------------------
登录成功后，后端签发一个 JWT 给前端。前端每次请求把它塞在
Authorization: Bearer <token> 头里，后端用它识别"这是哪个用户"。

JWT = "JSON Web Token"，一种无状态身份凭证。
真实项目里 SECRET_KEY 要放 .env，这里简化写死。
=====================================================================
"""

from datetime import datetime, timedelta

from jose import jwt, JWTError

from config import settings

ALGORITHM = "HS256"                 # 签名算法
TOKEN_EXPIRE_HOURS = 24             # token 有效期 24 小时


def create_token(user_id: int, username: str) -> str:
    """登录成功时调用：生成一个 JWT。"""
    expire = datetime.utcnow() + timedelta(hours=TOKEN_EXPIRE_HOURS)
    payload = {
        "sub": str(user_id),
        "username": username,
        "exp": expire,
    }
    return jwt.encode(payload, settings.JWT_SECRET_KEY, algorithm=ALGORITHM)


def decode_token(token: str) -> dict | None:
    """每次请求进来时调用：把 JWT 解开，取出里面的用户信息。"""
    try:
        payload = jwt.decode(token, settings.JWT_SECRET_KEY, algorithms=[ALGORITHM])
        return payload
    except JWTError:
        return None
