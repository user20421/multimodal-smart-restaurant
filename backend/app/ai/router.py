"""
智能聊天路由（AI 模块）

前缀 /api/v1/ai，与传统后端路由完全隔离。
鉴权复用传统后端的 get_current_user（仅 import 调用，不修改）。
当前能力：
- 文本对话：百炼大模型 + RAG 知识库检索增强
- 图片搜菜：智谱视觉模型识别 + 本店菜单比对（image_base64 触发）
"""
import asyncio
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.logging_config import get_logger
from app.ai.image_search import (
    NOT_FOOD_REPLY,
    analyze_food_image,
    build_answer_messages,
)
from app.ai.llm.bailian import get_chat_llm, SYSTEM_PROMPT
from app.ai.rag.retriever import get_context
from app.ai.schemas import AiChatRequest, AiChatResponse

logger = get_logger(__name__)

router = APIRouter()


async def _retrieve_context(query: str) -> str:
    """在线程池中执行 RAG 检索（Chroma/embedding 为阻塞调用），失败时降级为空。"""
    try:
        return await asyncio.to_thread(get_context, query)
    except Exception as e:
        logger.warning(f"[AI Chat] 知识库检索失败，降级为无上下文: {e}")
        return ""


def _build_messages(data: AiChatRequest, context: str = "") -> list:
    """构造发给大模型的消息列表（单轮对话 + RAG 检索上下文）。"""
    system = SYSTEM_PROMPT
    if context:
        system += (
            "\n\n以下是与顾客问题相关的本店真实资料，请优先根据资料回答；"
            "资料中没有的内容不要编造：\n" + context
        )
    return [
        SystemMessage(content=system),
        HumanMessage(content=data.message),
    ]


def _normalize_content(content) -> str:
    """兼容不同模型返回的内容形态（str 或 list）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(p) for p in content)
    return str(content or "")


async def _build_reply_messages(
    db: AsyncSession, data: AiChatRequest
) -> tuple[list | None, str | None]:
    """
    构造本轮对话的消息列表。
    返回 (messages, direct_reply)：direct_reply 非空时直接回复该文本（无需调 LLM）。
    """
    # 图片搜菜分支
    if data.image_base64:
        analysis = await analyze_food_image(data.image_base64)
        if not analysis["is_food"]:
            return None, NOT_FOOD_REPLY
        return await build_answer_messages(db, analysis, data.message), None

    # 普通文本分支：RAG 检索增强
    context = await _retrieve_context(data.message)
    return _build_messages(data, context), None


@router.post("/chat", response_model=AiChatResponse)
async def ai_chat(
    data: AiChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """智能聊天（同步 JSON 返回）"""
    if not data.message.strip() and not data.image_base64:
        return AiChatResponse(response="请问有什么可以帮您？", cart=data.cart)

    messages, direct_reply = await _build_reply_messages(db, data)
    if direct_reply is not None:
        return AiChatResponse(response=direct_reply, cart=data.cart)

    llm = get_chat_llm()
    result = await llm.ainvoke(messages)
    return AiChatResponse(response=_normalize_content(result.content), cart=data.cart)


@router.post("/chat/stream")
async def ai_chat_stream(
    data: AiChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """智能聊天（SSE 流式输出，对接前端聊天壳子）"""

    async def event_generator():
        try:
            if not data.message.strip() and not data.image_base64:
                payload = json.dumps(
                    {"type": "text", "content": "请问有什么可以帮您？"}, ensure_ascii=False
                )
                yield f"data: {payload}\n\n"
            else:
                messages, direct_reply = await _build_reply_messages(db, data)
                if direct_reply is not None:
                    # 固定回复（如非菜品提示），作为单个文本块发送
                    payload = json.dumps(
                        {"type": "text", "content": direct_reply}, ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
                else:
                    llm = get_chat_llm(streaming=True)
                    async for chunk in llm.astream(messages):
                        content = _normalize_content(chunk.content)
                        if content:
                            payload = json.dumps(
                                {"type": "text", "content": content}, ensure_ascii=False
                            )
                            yield f"data: {payload}\n\n"

            # 结束事件：购物车原样回显（图片搜菜不做购物车操作）
            done_payload = json.dumps({"type": "done", "cart": data.cart}, ensure_ascii=False)
            yield f"data: {done_payload}\n\n"

        except Exception as e:
            logger.exception(f"[AI ChatStream] 处理失败: {e}")
            err_payload = json.dumps({"type": "error", "message": str(e)}, ensure_ascii=False)
            yield f"data: {err_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
