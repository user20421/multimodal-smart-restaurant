"""
聊天相关 Schema
前端智能点餐助手调用 /chat 接口，当前版本仅保留下单等基础规则响应。
"""
from pydantic import BaseModel, Field
from typing import Optional, List, Dict, Any


class ChatRequest(BaseModel):
    user_id: int
    message: str
    cart: Optional[List[Dict[str, Any]]] = []
    image_base64: Optional[str] = None


class ChatResponse(BaseModel):
    response: str
    cart: List[Dict[str, Any]] = []
    intent: Optional[str] = None
    agent: Optional[str] = None
