"""
认证路由
保持与原后端API格式兼容
"""
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.exceptions import AuthenticationException, BusinessException
from app.api.deps import get_current_user
from app.schemas.auth import UserRegister, UserLogin, UserOut, AuthResponse, ChangePasswordRequest, UserProfileUpdate, FaceLoginRequest, FaceRegisterRequest
from app.services.auth_service import register_user, login_user, create_access_token, change_password, get_user_profile, update_user_profile, face_login_user, register_face
from app.services.captcha_service import create_captcha, verify_captcha

router = APIRouter()


@router.post("/auth/register")
async def register(data: UserRegister, db: AsyncSession = Depends(get_db)):
    """用户注册"""
    try:
        user = await register_user(db, data)
        return {"message": "注册成功", "user": user}
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/auth/captcha")
async def captcha():
    """获取图片验证码"""
    return await create_captcha()


@router.post("/auth/login", response_model=AuthResponse)
async def login(data: UserLogin, db: AsyncSession = Depends(get_db)):
    """用户登录（需先通过验证码校验）"""
    if not data.captcha_id or not data.captcha_code:
        raise HTTPException(status_code=400, detail="请输入验证码")

    valid = await verify_captcha(data.captcha_id, data.captcha_code)
    if not valid:
        raise HTTPException(status_code=400, detail="验证码错误或已过期")

    try:
        result = await login_user(db, data)
        token = create_access_token(result.id, result.role)
        return AuthResponse(user=result, message="登录成功", token=token)
    except AuthenticationException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/auth/change-password", response_model=UserOut)
async def change_password_endpoint(
    data: ChangePasswordRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """修改当前登录用户密码"""
    try:
        user = await change_password(db, current_user["id"], data)
        return user
    except AuthenticationException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/auth/face-login", response_model=AuthResponse)
async def face_login(data: FaceLoginRequest, db: AsyncSession = Depends(get_db)):
    """人脸识别登录"""
    try:
        user, distance = await face_login_user(db, data)
        token = create_access_token(user.id, user.role)
        # 直接根据欧氏距离计算相似度：distance=0 -> 100%，distance=1 -> 0%
        similarity = round((1 - distance) * 100, 1)
        return AuthResponse(
            user=user,
            message="人脸登录成功",
            token=token,
            similarity=similarity,
        )
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.post("/auth/face-register", response_model=UserOut)
async def face_register(
    data: FaceRegisterRequest,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """为当前登录用户录入人脸"""
    try:
        user = await register_face(db, current_user["id"], data)
        return user
    except AuthenticationException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.get("/auth/profile", response_model=UserOut)
async def get_profile(
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """获取当前登录用户资料"""
    try:
        user = await get_user_profile(db, current_user["id"])
        return user
    except AuthenticationException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)


@router.put("/auth/profile", response_model=UserOut)
async def update_profile(
    data: UserProfileUpdate,
    current_user: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """更新当前登录用户资料"""
    try:
        user = await update_user_profile(db, current_user["id"], data)
        # 同步更新前端缓存中的用户信息
        return user
    except AuthenticationException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
    except BusinessException as e:
        raise HTTPException(status_code=e.status_code, detail=e.message)
