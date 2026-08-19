"""Agent 工具层：菜单检索 / 购物车操作 / 下单 / 订单查询 / RAG 知识库检索"""
from app.ai.agent.context import AgentContext
from app.ai.agent.tools.cart_tools import build_cart_tools
from app.ai.agent.tools.menu_tools import build_menu_tools
from app.ai.agent.tools.order_tools import build_order_tools, build_place_order_tool
from app.ai.agent.tools.rag_tool import build_rag_tools


def build_tools(ctx: AgentContext) -> list:
    """请求级工具闭包工厂：所有工具共享同一个 AgentContext。"""
    return [
        *build_menu_tools(ctx),
        *build_cart_tools(ctx),
        *build_place_order_tool(ctx),
        *build_order_tools(ctx),
        *build_rag_tools(ctx),
    ]
