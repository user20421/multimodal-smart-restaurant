"""
Agent 请求级上下文

每次聊天请求创建一个 AgentContext，工具通过闭包工厂（build_tools）拿到它。
购物车是可变状态：从请求快照深拷贝而来，工具在其上修改，
最终由路由层在 done 事件中返回给前端（单一事实源仍是前端 Pinia）。
"""
from dataclasses import dataclass, field
from typing import Any, Dict, List

from sqlalchemy.ext.asyncio import AsyncSession


@dataclass
class AgentContext:
    db: AsyncSession
    user_id: int
    # 购物车快照（元素: {"menu_item_id","name","quantity","unit_price"}）
    cart: List[Dict[str, Any]] = field(default_factory=list)
    dirty: bool = False  # 购物车是否被本次对话修改过
