"""
Agent 提示词加载器

每个角色一个 Markdown 文件，便于独立维护与调优：
- router.md     路由分类节点
- cart.md       购物车专员（写操作，仅依据本句）
- order.md      订单专员（下单/查单，仅依据本句）
- knowledge.md  资讯顾问（只读咨询，可结合历史）
- chitchat.md   闲聊（引回餐厅话题）
- manager.md    餐厅经理（混合意图，全工具，更强模型，仅依据本句执行写操作）
"""
from pathlib import Path

_DIR = Path(__file__).resolve().parent


def _load(name: str) -> str:
    return (_DIR / f"{name}.md").read_text(encoding="utf-8").strip()


ROUTER_PROMPT = _load("router")
CART_AGENT_PROMPT = _load("cart")
ORDER_AGENT_PROMPT = _load("order")
KNOWLEDGE_AGENT_PROMPT = _load("knowledge")
CHITCHAT_PROMPT = _load("chitchat")
MANAGER_PROMPT = _load("manager")
