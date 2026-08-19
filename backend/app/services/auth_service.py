"""
认证服务
"""
import bcrypt
import jwt
from datetime import datetime, timezone, timedelta
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional

from app.repositories.user_repo import user_repo
from app.schemas.auth import UserRegister, UserLogin, UserOut, ChangePasswordRequest, UserProfileUpdate, FaceLoginRequest, FaceRegisterRequest
from app.core.exceptions import AuthenticationException, BusinessException
from app.core.config import settings
from app.services.face_service import (
    extract_face_encoding,
    encoding_to_list,
    find_best_face_match,
    encoding_from_list,
)
from app.core.logging_config import get_logger

logger = get_logger(__name__)


# 默认管理员账号（由项目根目录 init.sql 创建，登录后强制修改密码）
DEFAULT_ADMIN_USERNAME = "root"
DEFAULT_ADMIN_PASSWORD = "123456"

# 超级管理员账号（由项目根目录 init.sql 创建，仅用于重置管理员密码）
SUPER_ADMIN_USERNAME = "rootroot"
SUPER_ADMIN_INITIAL_PASSWORD = "rootroot"


def create_access_token(user_id: int, role: str) -> str:
    """生成 JWT 访问令牌"""
    expire = datetime.now(timezone.utc) + timedelta(hours=settings.jwt_access_token_expire_hours)
    payload = {
        "sub": str(user_id),
        "role": role,
        "exp": expire,
        "iat": datetime.now(timezone.utc),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def _hash_password(password: str) -> str:
    """bcrypt 哈希密码"""
    return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()


def _verify_password(password: str, hashed: str) -> bool:
    """校验 bcrypt 密码"""
    return bcrypt.checkpw(password.encode(), hashed.encode())


def _is_default_admin_credentials(username: str, password: str) -> bool:
    """判断是否为生产模式默认管理员凭据"""
    return username == DEFAULT_ADMIN_USERNAME and password == DEFAULT_ADMIN_PASSWORD


async def _check_project_activated(db: AsyncSession, username: str) -> None:
    """项目启用检查：超级管理员未修改初始密码时项目未启用，
    仅允许超级管理员本人登录（进入后强制修改密码），其他账号一律拒绝。
    """
    sa = await user_repo.get_by_username(db, SUPER_ADMIN_USERNAME)
    if sa and sa.need_change_password and username != SUPER_ADMIN_USERNAME:
        raise BusinessException("项目未启用，请联系开发人员")


async def register_user(db: AsyncSession, data: UserRegister) -> UserOut:
    """用户注册（首次注册不强制录入人脸）"""
    if data.username in ("admin", "管理员", DEFAULT_ADMIN_USERNAME, SUPER_ADMIN_USERNAME):
        raise BusinessException("该用户名已被系统保留，请更换")

    existing = await user_repo.get_by_username(db, data.username)
    if existing:
        raise BusinessException("用户名已存在")

    hashed = _hash_password(data.password)
    user = await user_repo.create(db, {
        "username": data.username,
        "password": hashed,
        "phone": data.phone,
        "gender": data.gender,
        "birth_date": data.birth_date,
        "role": "customer",
        "need_change_password": False,
        "face_encoding": None,
        "face_image_url": None,
    })
    await db.commit()
    return UserOut.model_validate(user)


async def login_user(db: AsyncSession, data: UserLogin) -> UserOut:
    """用户登录。默认管理员账号为 root/123456。"""
    lookup_name = data.username

    user = await user_repo.get_by_username(db, lookup_name)
    if not user:
        raise AuthenticationException("用户名或密码错误")

    if not _verify_password(data.password, user.password):
        raise AuthenticationException("用户名或密码错误")

    # 项目未启用（超管未改初始密码）时，除超管本人外一律拒绝登录
    await _check_project_activated(db, data.username)

    # 保护默认管理员账号：如果角色被篡改，自动纠正
    if user.username == DEFAULT_ADMIN_USERNAME and user.role != "admin":
        user.role = "admin"
        await db.commit()
        logger.info("[Auth] 登录时修复默认管理员角色为 admin")

    # 如果是默认管理员凭据登录，标记需要强制修改密码
    if _is_default_admin_credentials(data.username, data.password):
        user.need_change_password = True
        await db.commit()
    else:
        # 非默认凭据登录时，如果已修改过密码，取消强制修改标记
        if user.need_change_password and user.username == DEFAULT_ADMIN_USERNAME:
            user.need_change_password = False
            await db.commit()

    return UserOut.model_validate(user)


async def reset_admin_password(db: AsyncSession) -> None:
    """重置管理员 root 的密码为初始值 123456（仅超级管理员可调用）。"""
    user = await user_repo.get_by_username(db, DEFAULT_ADMIN_USERNAME)
    if not user:
        raise BusinessException("管理员账号 root 不存在")
    user.password = _hash_password(DEFAULT_ADMIN_PASSWORD)
    user.role = "admin"
    user.need_change_password = True  # 下次以初始密码登录后强制修改
    await db.commit()
    logger.info("[Auth] 超级管理员已将 root 密码重置为初始值")


async def change_password(
    db: AsyncSession,
    user_id: int,
    data: ChangePasswordRequest,
) -> UserOut:
    """修改密码。如果是首次强制修改密码状态，可不传旧密码。"""
    user = await user_repo.get(db, user_id)
    if not user:
        raise AuthenticationException("用户不存在")

    # 超级管理员仅允许在首次强制改密时修改一次密码
    if user.role == "superadmin":
        if not user.need_change_password:
            raise BusinessException("超级管理员密码仅允许修改一次")
        if data.new_password == SUPER_ADMIN_INITIAL_PASSWORD:
            raise BusinessException("新密码不能与初始密码相同")

    # 非强制修改密码场景下必须验证旧密码
    if not user.need_change_password:
        if not data.old_password:
            raise AuthenticationException("请输入旧密码")
        if not _verify_password(data.old_password, user.password):
            raise AuthenticationException("旧密码错误")

    user.password = _hash_password(data.new_password)
    user.need_change_password = False
    await db.commit()
    return UserOut.model_validate(user)


async def get_user_profile(db: AsyncSession, user_id: int) -> UserOut:
    """获取用户资料"""
    user = await user_repo.get(db, user_id)
    if not user:
        raise AuthenticationException("用户不存在")
    return UserOut.model_validate(user)


async def update_user_profile(
    db: AsyncSession, user_id: int, data: UserProfileUpdate
) -> UserOut:
    """更新用户资料（手机号、性别、出生日期）"""
    user = await user_repo.get(db, user_id)
    if not user:
        raise AuthenticationException("用户不存在")

    update_data = data.model_dump(exclude_unset=True)
    if not update_data:
        return UserOut.model_validate(user)

    if "gender" in update_data and update_data["gender"] not in (None, "unknown", "male", "female"):
        raise BusinessException("性别格式不正确，可选值：unknown/male/female")

    for key, value in update_data.items():
        setattr(user, key, value)

    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)


async def face_login_user(db: AsyncSession, data: FaceLoginRequest) -> tuple[UserOut, float]:
    """人脸登录：提取特征后与所有已录入人脸的用户比对。

    返回 (user, distance)，distance 为欧氏距离。
    """
    unknown_encoding = extract_face_encoding(data.face_image_base64)
    if unknown_encoding is None:
        raise BusinessException("未检测到人脸，请正对摄像头")

    users = await user_repo.get_users_with_face(db)
    if not users:
        raise BusinessException("人脸识别失败，请通过密码登录")

    candidates = [(u.id, encoding_from_list(u.face_encoding)) for u in users]
    match = find_best_face_match(unknown_encoding, candidates)
    if match is None:
        raise BusinessException("人脸识别失败，请通过密码登录")

    user_id, distance = match
    user = await user_repo.get(db, user_id)
    if not user:
        raise BusinessException("人脸识别失败，请通过密码登录")

    # 项目未启用（超管未改初始密码）时，除超管本人外一律拒绝登录
    await _check_project_activated(db, user.username)

    logger.info(f"[FaceLogin] 匹配用户 {user.username}，距离={distance:.4f}")
    return UserOut.model_validate(user), distance


async def register_face(
    db: AsyncSession, user_id: int, data: FaceRegisterRequest
) -> UserOut:
    """为当前登录用户录入/更新人脸（只存特征向量，不保存照片）。"""
    user = await user_repo.get(db, user_id)
    if not user:
        raise AuthenticationException("用户不存在")

    encoding = extract_face_encoding(data.face_image_base64)
    if encoding is None:
        raise BusinessException("未检测到人脸，请重新拍摄")

    # 隐私保护：不保存人脸照片，仅存储 128 维特征向量
    user.face_encoding = encoding_to_list(encoding)
    user.face_image_url = None

    await db.commit()
    await db.refresh(user)
    return UserOut.model_validate(user)
