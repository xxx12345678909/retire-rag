"""认证 API 路由"""

from fastapi import APIRouter, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from .auth_service import register, login, get_user_by_token

router = APIRouter(prefix="/api/auth")


class RegisterBody(BaseModel):
    username: str
    password: str
    phone: str | None = None


class LoginBody(BaseModel):
    username: str
    password: str


@router.post("/register")
async def route_register(body: RegisterBody):
    result = register(body.username, body.password, body.phone)
    if result["ok"]:
        return JSONResponse({"ok": True, "user_id": result["user_id"]}, status_code=201)
    return JSONResponse(result, status_code=400)


@router.post("/login")
async def route_login(body: LoginBody):
    result = login(body.username, body.password)
    if result["ok"]:
        return JSONResponse(result)
    return JSONResponse({"ok": False}, status_code=401)


@router.get("/me")
async def route_me(authorization: str = Header(None)):
    if authorization is None or not authorization.startswith("Bearer "):
        return JSONResponse({"error": "缺少认证令牌"}, status_code=401)

    token = authorization[len("Bearer "):]
    user = get_user_by_token(token)
    if user is None:
        return JSONResponse({"error": "无效或过期的令牌"}, status_code=401)

    return JSONResponse(user)
