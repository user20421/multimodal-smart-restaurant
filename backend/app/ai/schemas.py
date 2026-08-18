"""
AI 模块请求/响应模型（独立于传统后端 schemas）
"""
from typing import Any, Dict, List, Optional

from pydantic import BaseModel


class AiChatRequest(BaseModel):
    """聊天请求。兼容前端聊天壳子原有的载荷格式（多余字段忽略）。"""

    message: str = ""
    user_id: Optional[int] = None
    cart: List[Dict[str, Any]] = []
    image_base64: Optional[str] = None

    model_config = {"extra": "ignore"}


class AiChatResponse(BaseModel):
    """聊天响应（同步 JSON）。"""

    response: str
    cart: List[Dict[str, Any]] = []
