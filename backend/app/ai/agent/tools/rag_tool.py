"""RAG 知识库检索工具（包装现有 retriever，供 Agent 调用）"""
import asyncio

from langchain_core.tools import tool

from app.ai.agent.context import AgentContext
from app.ai.rag.retriever import get_context
from app.core.logging_config import get_logger

logger = get_logger(__name__)


def build_rag_tools(ctx: AgentContext) -> list:
    @tool("search_knowledge")
    async def search_knowledge(query: str) -> str:
        """检索本店知识库（店铺介绍、营业信息、菜品资料、FAQ、配送政策）。
        当用户询问店铺信息、菜品口味/推荐、配送、营业时间等问题时使用。
        """
        try:
            context = await asyncio.to_thread(get_context, query)
        except Exception as e:
            logger.warning(f"[RagTool] 知识库检索失败: {e}")
            return "知识库暂时不可用。"
        return context or "知识库中没有找到相关内容。"

    return [search_knowledge]
