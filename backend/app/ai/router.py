"""
智能聊天路由（AI 模块）
前缀 /api/v1/ai，与传统后端路由完全隔离。鉴权复用传统后端的 get_current_user（仅 import 调用，不修改）。
文本对话走分级管线：
- L1 正则快速路（agent/fastpath.py）：简单意图确定性处理，不调 LLM
- L2 多智能体图（agent/graph.py）：router 分类节点分发到购物车/订单/资讯/闲聊四个专员
对话历史持久化在 MongoDB（chat_store.py，必需依赖，启动时强校验连通性）。
图片搜菜分支保持不变：智谱视觉模型识别 + 本店菜单比对（image_base64 触发）。"""
import copy
import json

from fastapi import APIRouter, Depends
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_current_user
from app.core.database import get_db
from app.core.logging_config import get_logger
from app.ai import chat_store
from app.ai import config as ai_config
from app.ai import quota
from app.ai.agent import fastpath
from app.ai.agent.context import AgentContext
from app.ai.agent.graph import run_graph, stream_graph
from app.ai.fallback import FALLBACK_REPLY
from app.ai.image_search import (
    NOT_FOOD_REPLY,
    analyze_food_image,
    build_answer_messages,
)
from app.ai.llm.bailian import get_chat_llm
from app.ai.sanitize import sanitize_reply
from app.ai.schemas import AiChatRequest, AiChatResponse

logger = get_logger(__name__)

router = APIRouter()

# 快速路回复的打字机切分粒度（字符数）
_FASTPATH_CHUNK = 8


def _normalize_content(content) -> str:
    """兼容不同模型返回的内容形态（str 或 list）。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        return "".join(str(p) for p in content)
    return str(content or "")


def _make_context(db: AsyncSession, data: AiChatRequest, user_id: int) -> AgentContext:
    """从请求快照构建 Agent 上下文（深拷贝购物车，避免污染请求数据）。"""
    return AgentContext(db=db, user_id=user_id, message=data.message, cart=copy.deepcopy(data.cart))


def _bailian_ready() -> bool:
    """百炼大模型是否可用（API Key 与模型名称均已配置）。"""
    return bool(ai_config.BAILIAN_API_KEY and ai_config.BAILIAN_LLM_MODEL)


def _zhipu_ready() -> bool:
    """智谱视觉模型是否可用（API Key 与模型名称均已配置）。"""
    return bool(ai_config.ZHIPU_API_KEY and ai_config.ZHIPU_VISION_MODEL)


async def _handle_text(ctx: AgentContext, message: str, history: list) -> str:
    """文本消息处理（同步）：L1 快速路 -> L2 Agent。大模型不可用时返回友好兜底回复。"""
    reply = await fastpath.try_handle(ctx, message)
    if reply is not None:
        return reply
    if not _bailian_ready():
        logger.warning("[AI Chat] 未配置百炼 API Key 或模型名称，返回兜底回复")
        return FALLBACK_REPLY
    try:
        return sanitize_reply(await run_graph(ctx, message, history))
    except Exception as e:
        # 欠费 / 连接失败 / 模型报错等，兜底不影响传统点餐链路
        logger.exception(f"[AI Chat] 大模型调用失败，返回兜底回复: {e}")
        return FALLBACK_REPLY


async def _stream_text(ctx: AgentContext, message: str, history: list):
    """文本消息处理（流式）：yield {"type": "text"|"status", "content": ...}。"""
    reply = await fastpath.try_handle(ctx, message)
    if reply is not None:
        # 快速路也给打字机效果，前端体验一致
        for i in range(0, len(reply), _FASTPATH_CHUNK):
            yield {"type": "text", "content": reply[i : i + _FASTPATH_CHUNK]}
        return
    if not _bailian_ready():
        logger.warning("[AI ChatStream] 未配置百炼 API Key 或模型名称，返回兜底回复")
        for i in range(0, len(FALLBACK_REPLY), _FASTPATH_CHUNK):
            yield {"type": "text", "content": FALLBACK_REPLY[i : i + _FASTPATH_CHUNK]}
        return
    try:
        async for event in stream_graph(ctx, message, history):
            if event["type"] == "text":
                event["content"] = sanitize_reply(event["content"])
            if event["content"]:
                yield event
    except Exception as e:
        logger.exception(f"[AI ChatStream] 大模型调用失败，返回兜底回复: {e}")
        yield {"type": "text", "content": FALLBACK_REPLY}


async def _save_history(user_id: int, user_content: str, assistant_content: str) -> None:
    """保存本轮对话到 MongoDB（必需依赖，失败直接抛错）。"""
    await chat_store.append_history(
        user_id,
        [
            {"role": "user", "content": user_content},
            {"role": "assistant", "content": assistant_content},
        ],
    )


@router.post("/chat", response_model=AiChatResponse)
async def ai_chat(
    data: AiChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """智能聊天（同步 JSON 返回）"""
    if not data.message.strip() and not data.image_base64:
        return AiChatResponse(response="请问有什么可以帮您？", cart=data.cart)

    user_id = current_user["id"]

    # 普通用户每次发送扣减一次聊天次数（为 0 时抛业务异常，前端弹窗提示）
    if current_user.get("role") == "customer":
        await quota.consume_quota(db, user_id)

    # 图片搜菜分支（视觉 + 对话模型均不可用时直接兜底）
    if data.image_base64:
        if not (_zhipu_ready() and _bailian_ready()):
            logger.warning("[AI Chat] 图片搜菜模型未配置完整，返回兜底回复")
            return AiChatResponse(response=FALLBACK_REPLY, cart=data.cart)
        try:
            analysis = await analyze_food_image(data.image_base64)
            if not analysis["is_food"]:
                return AiChatResponse(response=NOT_FOOD_REPLY, cart=data.cart)
            messages = await build_answer_messages(db, analysis, data.message)
            llm = get_chat_llm()
            result = await llm.ainvoke(messages)
            reply = sanitize_reply(_normalize_content(result.content))
        except Exception as e:
            logger.exception(f"[AI Chat] 图片搜菜大模型调用失败，返回兜底回复: {e}")
            return AiChatResponse(response=FALLBACK_REPLY, cart=data.cart)
        await _save_history(user_id, data.message or "[图片搜菜]", reply)
        return AiChatResponse(response=reply, cart=data.cart)

    # 文本分支：L1 快速路 -> L2 Agent
    try:
        ctx = _make_context(db, data, user_id)
        history = await chat_store.load_history(user_id)
        reply = await _handle_text(ctx, data.message, history)
        reply = sanitize_reply(reply)
    except Exception as e:
        logger.exception(f"[AI Chat] 处理失败，返回兜底回复: {e}")
        return AiChatResponse(response=FALLBACK_REPLY, cart=data.cart)
    await _save_history(user_id, data.message, reply)
    return AiChatResponse(response=reply, cart=ctx.cart)


@router.delete("/chat/history")
async def ai_clear_chat_history(current_user: dict = Depends(get_current_user)):
    """清空当前用户的全部聊天记录（MongoDB，按 user_id 隔离）。"""
    deleted = await chat_store.clear_history(current_user["id"])
    return {"message": "聊天记录已清空", "deleted": deleted}


@router.post("/chat/stream")
async def ai_chat_stream(
    data: AiChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """智能聊天（SSE 流式输出，对接前端聊天壳子）"""

    async def event_generator():
        reply_parts: list[str] = []
        user_id = current_user["id"]
        # 默认回显请求购物车；文本分支会切换为 ctx.cart（含 AI 的修改）
        final_cart = data.cart
        user_content = data.message or ("[图片搜菜]" if data.image_base64 else "")
        # 普通用户每次发送扣减一次聊天次数（为 0 时抛业务异常，前端弹窗提示）
        if current_user.get("role") == "customer":
            await quota.consume_quota(db, user_id)
        try:
            if not data.message.strip() and not data.image_base64:
                text = "请问有什么可以帮您？"
                reply_parts.append(text)
                yield f"data: {json.dumps({'type': 'text', 'content': text}, ensure_ascii=False)}\n\n"

            elif data.image_base64:
                # 图片搜菜分支（视觉 + 对话模型均不可用时直接兜底）
                if not (_zhipu_ready() and _bailian_ready()):
                    logger.warning("[AI ChatStream] 图片搜菜模型未配置完整，返回兜底回复")
                    reply_parts.append(FALLBACK_REPLY)
                    payload = json.dumps(
                        {"type": "text", "content": FALLBACK_REPLY}, ensure_ascii=False
                    )
                    yield f"data: {payload}\n\n"
                else:
                    try:
                        analysis = await analyze_food_image(data.image_base64)
                    except Exception as e:
                        logger.exception(f"[AI ChatStream] 图片搜菜大模型调用失败，返回兜底回复: {e}")
                        analysis = None
                    if analysis is None:
                        reply_parts.append(FALLBACK_REPLY)
                        payload = json.dumps(
                            {"type": "text", "content": FALLBACK_REPLY}, ensure_ascii=False
                        )
                        yield f"data: {payload}\n\n"
                    elif not analysis["is_food"]:
                        reply_parts.append(NOT_FOOD_REPLY)
                        payload = json.dumps(
                            {"type": "text", "content": NOT_FOOD_REPLY}, ensure_ascii=False
                        )
                        yield f"data: {payload}\n\n"
                    else:
                        messages = await build_answer_messages(db, analysis, data.message)
                        llm = get_chat_llm(streaming=True)
                        async for chunk in llm.astream(messages):
                            content = sanitize_reply(_normalize_content(chunk.content))
                            if content:
                                reply_parts.append(content)
                                payload = json.dumps(
                                    {"type": "text", "content": content}, ensure_ascii=False
                                )
                                yield f"data: {payload}\n\n"

            else:
                # 文本分支：L1 快速路 -> L2 Agent
                ctx = _make_context(db, data, user_id)
                final_cart = ctx.cart
                history = await chat_store.load_history(user_id)
                async for event in _stream_text(ctx, data.message, history):
                    if event["type"] == "text":
                        reply_parts.append(event["content"])
                    yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"

            # 保存本轮对话历史（MongoDB）
            full_reply = "".join(reply_parts)
            if user_content and full_reply:
                await _save_history(user_id, user_content, full_reply)

            # 结束事件：携带最终购物车（AI 有修改则为修改后的快照）
            done_payload = json.dumps({"type": "done", "cart": final_cart}, ensure_ascii=False)
            yield f"data: {done_payload}\n\n"

        except Exception as e:
            logger.exception(f"[AI ChatStream] 处理失败，返回兜底回复: {e}")
            if not reply_parts:
                reply_parts.append(FALLBACK_REPLY)
                err_payload = json.dumps(
                    {"type": "text", "content": FALLBACK_REPLY}, ensure_ascii=False
                )
                yield f"data: {err_payload}\n\n"
            done_payload = json.dumps({"type": "done", "cart": final_cart}, ensure_ascii=False)
            yield f"data: {done_payload}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )
