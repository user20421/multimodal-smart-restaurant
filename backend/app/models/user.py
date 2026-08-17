"""
用户模型
"""
from sqlalchemy import Column, Integer, String, DateTime, Boolean, Date, JSON, func
from sqlalchemy.orm import relationship

from app.core.database import Base


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    username = Column(String(50), unique=True, nullable=False, comment="用户名")
    password = Column(String(200), nullable=False, comment="密码bcrypt哈希")
    role = Column(String(20), default="customer", comment="角色: customer/admin")
    phone = Column(String(20), nullable=True, comment="手机号")
    gender = Column(String(10), nullable=True, comment="性别: male/female")
    birth_date = Column(Date, nullable=True, comment="出生日期")
    need_change_password = Column(
        Boolean,
        default=False,
        comment="是否需要强制修改密码（生产模式：默认管理员首次登录后必须修改）",
    )
    face_encoding = Column(JSON, nullable=True, comment="人脸特征向量（128维）")
    face_image_url = Column(String(255), nullable=True, comment="人脸头像存储路径")
    created_at = Column(DateTime, server_default=func.now(), comment="创建时间")
    updated_at = Column(DateTime, server_default=func.now(), onupdate=func.now(), comment="更新时间")

    # 关联
    orders = relationship("Order", back_populates="user", cascade="all, delete-orphan")
