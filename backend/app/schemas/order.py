"""
订单相关Schema
"""
from pydantic import BaseModel, Field, field_serializer
from typing import Optional, List
from datetime import datetime

from app.utils.formatters import utc_to_local


class CartItem(BaseModel):
    menu_item_id: int
    name: str
    quantity: int = Field(..., gt=0)
    unit_price: float


class OrderItemOut(BaseModel):
    id: int
    menu_item_id: int
    name: str
    quantity: int
    unit_price: float
    subtotal: float

    model_config = {"from_attributes": True}


class OrderCreate(BaseModel):
    items: List[CartItem]
    remark: Optional[str] = None


class OrderOut(BaseModel):
    id: int
    user_id: int
    username: Optional[str] = None  # 脱敏后的用户名，如 刘**
    status: str
    total_price: float
    remark: Optional[str] = None
    items: List[OrderItemOut] = []
    created_at: datetime
    updated_at: datetime

    @field_serializer("created_at", "updated_at")
    def _serialize_local_time(self, dt: datetime) -> datetime:
        """数据库存 UTC，输出统一转东八区本地时间（覆盖 API 返回与 PDF 导出）"""
        return utc_to_local(dt)

    model_config = {"from_attributes": True}


class PaginatedOrdersResponse(BaseModel):
    items: List[OrderOut]
    total: int
    page: int
    page_size: int
