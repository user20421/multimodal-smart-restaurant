"""
多智能体图编排（L2）

结构：
    START -> router（LLM 分类节点，只看本句，输出六类标签）
          -> cart_node      购物车专员（带历史；写操作由提示词强约束只能依据本句）
          -> order_node     订单专员（只读查询，带历史以理解"那笔订单"等指代）
          -> knowledge_node 资讯顾问（只读，可带历史）
          -> chitchat_node  闲聊节点（无工具，可带历史）
          -> manager_node   餐厅经理（混合意图，全工具，更强模型 BAILIAN_LLM_MODEL_X）
          -> unclear_node   固定话术：请用户说清楚

设计要点：
- 每个请求构建一次编译图，节点为闭包，共享同一个 AgentContext；
- 查询（只读）可以结合对话历史理解指代；增删改/下单等写操作只依据用户当前这句话，
  指代历史内容（如"刚才那个菜再来一份"）时必须请用户一句话说清楚，不得猜测执行；
- 提示词独立维护在 prompts/ 目录的 Markdown 文件中；
- 流式：astream_events 按 langgraph_node 过滤，router 的内部分类 token 不外泄。
"""
from typing import Any, AsyncIterator, Dict, List, TypedDict

from langchain.agents import create_agent
from langchain_core.messages import AIMessage, BaseMessage, HumanMessage, SystemMessage
from langgraph.graph import END, START, StateGraph

from app.ai.agent.context import AgentContext
from app.ai.agent.prompts import (
    CART_AGENT_PROMPT,
    CHITCHAT_PROMPT,
    KNOWLEDGE_AGENT_PROMPT,
    MANAGER_PROMPT,
    ORDER_AGENT_PROMPT,
    ROUTER_PROMPT,
)
from app.ai.agent.tools.cart_tools import build_cart_tools, cart_summary_text
from app.ai.agent.tools.menu_tools import build_menu_tools
from app.ai.agent.tools.order_tools import build_order_tools, build_place_order_tool
from app.ai.agent.tools.rag_tool import build_rag_tools
from app.ai.llm.bailian import get_chat_llm, get_chat_llm_x

# 工具开始执行时的状态提示（SSE status 事件，不使用表情符号）
_TOOL_STATUS_TEXT = {
    "search_dish": "正在查询菜单…",
    "add_to_cart": "正在加入购物车…",
    "remove_from_cart": "正在更新购物车…",
    "set_dish_quantity": "正在更新购物车…",
    "clear_cart": "正在清空购物车…",
    "place_order": "正在为您下单…",
    "list_recent_orders": "正在查询订单…",
    "list_orders_last_days": "正在查询订单…",
    "list_orders_on_date": "正在查询订单…",
    "search_knowledge": "正在查阅资料…",
}

# 允许向用户流式输出 token 的节点（router 的分类 token 绝不外泄）
_STREAM_NODES = {"cart_node", "order_node", "knowledge_node", "chitchat_node", "manager_node"}

_ROUTES = ("cart", "order", "knowledge", "chitchat", "manager", "unclear")

# 经理节点的图递归步数上限（每次工具调用约占 2 步）：混合意图通常 3~5 次工具调用，
# 20 步足够覆盖且能防止模型异常时的工具调用死循环（控制成本与耗时）
_MANAGER_RECURSION_LIMIT = 20

UNCLEAR_REPLY = (
    "抱歉，我没有完全理解您的需求。"
    "涉及加菜、减菜、下单等操作时，请在一句话里说明具体的菜品名称和数量，"
    "例如：来两份宫保鸡丁。"
)


class GraphState(TypedDict):
    message: str  # 用户当前这句话
    history: List[Dict[str, Any]]  # MongoDB 历史（查询类节点用于理解指代；写操作不得依据历史）
    route: str
    reply: str


def _normalize_content(content: Any) -> str:
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(p) for p in content)
    return str(content or "")


def _history_to_messages(history: List[Dict[str, Any]]) -> List[BaseMessage]:
    """MongoDB 历史记录 -> LangChain 消息（user/assistant；system 为滚动摘要注入）。"""
    messages: List[BaseMessage] = []
    for h in history:
        role, content = h.get("role"), str(h.get("content") or "")
        if not content:
            continue
        if role == "user":
            messages.append(HumanMessage(content=content))
        elif role == "assistant":
            messages.append(AIMessage(content=content))
        elif role == "system":
            messages.append(SystemMessage(content=content))
    return messages


def _parse_route(text: str) -> str:
    """解析路由节点的输出标签，无法识别时降级为 unclear。"""
    t = _normalize_content(text).strip().lower().strip("。.,，!！?？ \t\"'`")
    for label in _ROUTES:
        if t.startswith(label):
            return label
    for label in _ROUTES:
        if label in t:
            return label
    return "unclear"


# 写能力节点（cart/manager）的确定性提示：贴近生成点注入，强化两条类级规则——
# 信息齐全就直接执行（禁止"要我加吗"式悬空确认：其简短回答无法被单句路由正确处理），
# 以及未接地不声称（工具未成功前不得声称完成）。
_WRITE_NODE_NOTE = (
    "[系统提示] 本句信息齐全时直接调用工具执行并汇报结果，不要就是否执行向用户反问是非确认"
    "（如'要我加吗''您是要……吗'）；未调用工具或工具未执行成功时，回复不得声称已完成任何操作。"
)

# 无写能力节点（order/knowledge/chitchat）的确定性接地提示：注入在用户消息最前面
# （位于历史之后、生成之前），防止节点被历史中的待办话题诱导，
# 声称执行了自己根本没有的写操作能力（"好的，已为您记录"类幻觉）。
_NO_WRITE_GROUNDING_NOTE = (
    "[系统提示] 你不具备、本轮也不会执行任何购物车或订单的写操作"
    "（加菜/减菜/改数量/清空/下单）。若用户这句话只是对之前话题的简短回应"
    "（如'是的''好的''可以'），不得声称已记录、已加菜、已下单或已移除任何内容；"
    "如实说明尚未做任何操作，并引导用户用一句完整的话说出需求"
    "（包含菜品名称和数量，如'来两份宫保鸡丁'）。"
)


def _cart_context_message(ctx: AgentContext, message: str) -> HumanMessage:
    """写能力节点（cart/manager）：确定性提示 + 购物车快照作为前缀并入用户消息。"""
    return HumanMessage(
        content=f"{_WRITE_NODE_NOTE}\n\n[上下文] {cart_summary_text(ctx.cart)}\n\n{message}"
    )


def _no_write_context_message(message: str) -> HumanMessage:
    """无写能力节点（knowledge/chitchat）：确定性注入接地提示。"""
    return HumanMessage(content=f"{_NO_WRITE_GROUNDING_NOTE}\n\n{message}")


def _readonly_context_message(ctx: AgentContext, message: str) -> HumanMessage:
    """只读查询节点（order）：确定性接地提示 + 购物车快照上下文。"""
    return HumanMessage(
        content=f"{_NO_WRITE_GROUNDING_NOTE}\n\n[上下文] {cart_summary_text(ctx.cart)}\n\n{message}"
    )


def build_graph(ctx: AgentContext):
    """为单次请求构建编译后的多智能体图。"""
    # 购物车专员：购物车写操作 + 下单（下单是“购物车 -> 订单”的写操作）
    cart_agent = create_agent(
        get_chat_llm(streaming=True),
        [*build_menu_tools(ctx), *build_cart_tools(ctx), *build_place_order_tool(ctx)],
        system_prompt=CART_AGENT_PROMPT,
    )
    # 订单专员：只读查询已下单的订单（进行中/已完成）
    order_agent = create_agent(
        get_chat_llm(streaming=True),
        [*build_order_tools(ctx)],
        system_prompt=ORDER_AGENT_PROMPT,
    )
    knowledge_agent = create_agent(
        get_chat_llm(streaming=True),
        [*build_menu_tools(ctx), *build_rag_tools(ctx)],
        system_prompt=KNOWLEDGE_AGENT_PROMPT,
    )
    # 餐厅经理：混合意图专用，装备全部专员的工具，使用更强模型（BAILIAN_LLM_MODEL_X）。
    # 写操作硬约束由工具闭包内的 guard_write_op 等确定性校验保证，与专员一致。
    manager_agent = create_agent(
        get_chat_llm_x(streaming=True),
        [
            *build_menu_tools(ctx),
            *build_cart_tools(ctx),
            *build_place_order_tool(ctx),
            *build_order_tools(ctx),
            *build_rag_tools(ctx),
        ],
        system_prompt=MANAGER_PROMPT,
    )

    async def router_node(state: GraphState) -> dict:
        """LLM 分类：只看当前这句话，拿不准就是 unclear。"""
        llm = get_chat_llm()
        result = await llm.ainvoke(
            [SystemMessage(content=ROUTER_PROMPT), HumanMessage(content=state["message"])]
        )
        return {"route": _parse_route(result.content)}

    async def cart_node(state: GraphState) -> dict:
        # 带历史（查询可理解指代）；写操作由提示词强约束：只能依据本句，指代不清须追问
        messages = [
            *_history_to_messages(state["history"]),
            _cart_context_message(ctx, state["message"]),
        ]
        result = await cart_agent.ainvoke({"messages": messages})
        return {"reply": _normalize_content(result["messages"][-1].content)}

    async def order_node(state: GraphState) -> dict:
        # 订单专员为只读查询：带历史以理解“那笔订单”等指代
        messages = [
            *_history_to_messages(state["history"]),
            _readonly_context_message(ctx, state["message"]),
        ]
        result = await order_agent.ainvoke({"messages": messages})
        return {"reply": _normalize_content(result["messages"][-1].content)}

    async def knowledge_node(state: GraphState) -> dict:
        # 只读咨询：可以带历史理解"这道菜"之类的指代
        messages = [
            *_history_to_messages(state["history"]),
            _no_write_context_message(state["message"]),
        ]
        result = await knowledge_agent.ainvoke({"messages": messages})
        return {"reply": _normalize_content(result["messages"][-1].content)}

    async def chitchat_node(state: GraphState) -> dict:
        llm = get_chat_llm(streaming=True)
        messages = [
            SystemMessage(content=CHITCHAT_PROMPT),
            *_history_to_messages(state["history"]),
            _no_write_context_message(state["message"]),
        ]
        parts: list[str] = []
        async for chunk in llm.astream(messages):
            parts.append(_normalize_content(chunk.content))
        return {"reply": "".join(parts)}

    async def manager_node(state: GraphState) -> dict:
        # 餐厅经理：带历史（查询可理解指代）+ 购物车快照上下文；
        # 写操作只依据本句（提示词强约束 + 工具层硬校验双重保证）；
        # recursion_limit 限制工具调用预算，防止异常死循环
        messages = [
            *_history_to_messages(state["history"]),
            _cart_context_message(ctx, state["message"]),
        ]
        result = await manager_agent.ainvoke(
            {"messages": messages},
            config={"recursion_limit": _MANAGER_RECURSION_LIMIT},
        )
        return {"reply": _normalize_content(result["messages"][-1].content)}

    async def unclear_node(state: GraphState) -> dict:
        return {"reply": UNCLEAR_REPLY}

    def _route_edge(state: GraphState) -> str:
        return {
            "cart": "cart_node",
            "order": "order_node",
            "knowledge": "knowledge_node",
            "chitchat": "chitchat_node",
            "manager": "manager_node",
        }.get(state["route"], "unclear_node")

    graph = StateGraph(GraphState)
    graph.add_node(router_node)
    graph.add_node(cart_node)
    graph.add_node(order_node)
    graph.add_node(knowledge_node)
    graph.add_node(chitchat_node)
    graph.add_node(manager_node)
    graph.add_node(unclear_node)
    graph.add_edge(START, "router_node")
    graph.add_conditional_edges("router_node", _route_edge)
    for node in (
        "cart_node",
        "order_node",
        "knowledge_node",
        "chitchat_node",
        "manager_node",
        "unclear_node",
    ):
        graph.add_edge(node, END)
    return graph.compile()


def _initial_state(message: str, history: List[Dict[str, Any]]) -> GraphState:
    return GraphState(message=message, history=history, route="", reply="")


async def run_graph(ctx: AgentContext, message: str, history: List[Dict[str, Any]]) -> str:
    """同步执行图，返回最终回复文本。"""
    result = await build_graph(ctx).ainvoke(_initial_state(message, history))
    return result.get("reply") or UNCLEAR_REPLY


async def stream_graph(
    ctx: AgentContext, message: str, history: List[Dict[str, Any]]
) -> AsyncIterator[Dict[str, str]]:
    """流式执行图，yield {"type": "text"|"status", "content": ...} 事件。"""
    streamed = False
    final_reply = ""
    async for event in build_graph(ctx).astream_events(
        _initial_state(message, history), version="v2"
    ):
        kind = event.get("event")
        node = event.get("metadata", {}).get("langgraph_node", "")
        if kind == "on_chat_model_stream" and node in _STREAM_NODES:
            content = _normalize_content(event["data"]["chunk"].content)
            if content:
                streamed = True
                yield {"type": "text", "content": content}
        elif kind == "on_tool_start":
            status = _TOOL_STATUS_TEXT.get(event.get("name", ""))
            if status:
                yield {"type": "status", "content": status}
        elif kind == "on_chain_end" and event.get("name") == "LangGraph":
            output = event.get("data", {}).get("output") or {}
            final_reply = output.get("reply", "")

    # 节点没有流式输出（如 unclear 固定话术）时，图结束后补发最终回复
    if not streamed and final_reply:
        for i in range(0, len(final_reply), 8):
            yield {"type": "text", "content": final_reply[i : i + 8]}
