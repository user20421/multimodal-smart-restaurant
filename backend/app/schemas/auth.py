"""
认证相关Schema
"""
from pydantic import BaseModel, Field, model_validator
from typing import Optional, Any
from datetime import date


class UserRegister(BaseModel):
    username: str = Field(..., min_length=3, max_length=50, description="用户名")
    password: str = Field(..., min_length=6, max_length=100, description="密码")
    phone: Optional[str] = Field(None, description="手机号")
    gender: str = Field(..., pattern="^(unknown|male|female)$", description="性别: unknown/male/female")
    birth_date: Optional[date] = Field(None, description="出生日期")


class UserLogin(BaseModel):
    username: str = Field(..., description="用户名")
    password: str = Field(..., description="密码")
    role: Optional[str] = Field(None, description="角色（已废弃，保留兼容）")
    captcha_id: Optional[str] = Field(None, description="验证码 ID")
    captcha_code: Optional[str] = Field(None, description="验证码字符")


class UserOut(BaseModel):
    id: int
    username: str
    role: str
    phone: Optional[str] = None
    gender: Optional[str] = None
    birth_date: Optional[date] = None
    need_change_password: bool = False
    has_face: bool = False
    face_encoding: Optional[Any] = Field(None, exclude=True)

    model_config = {"from_attributes": True}

    @model_validator(mode="after")
    def _compute_has_face(self):
        self.has_face = bool(self.face_encoding)
        return self


class AuthResponse(BaseModel):
    user: UserOut
    message: str
    token: Optional[str] = None
    similarity: Optional[float] = Field(None, description="人脸相似度百分比 0-100")


class ChangePasswordRequest(BaseModel):
    old_password: Optional[str] = Field(None, description="旧密码（首次强制修改时可不传）")
    new_password: str = Field(..., min_length=6, max_length=100, description="新密码")


class UserProfileUpdate(BaseModel):
    phone: Optional[str] = Field(None, description="手机号")
    gender: Optional[str] = Field(None, pattern="^(unknown|male|female)$", description="性别: unknown/male/female")
    birth_date: Optional[date] = Field(None, description="出生日期")


class FaceLoginRequest(BaseModel):
    face_image_base64: str = Field(..., description="人脸照片 base64（含 data URI）")


class FaceRegisterRequest(BaseModel):
    face_image_base64: str = Field(..., description="人脸照片 base64（含 data URI）")
