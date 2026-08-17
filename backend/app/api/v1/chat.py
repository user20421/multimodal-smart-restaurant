"""
聊天路由（传统规则版本）
为兼容前端保留的智能点餐助手 UI，提供 /chat 和 /chat/stream 接口。
当前版本仅处理下单、查看购物车、清空购物车等基础意图，不调用任何 AI/LLM。
"""
import json
import asyncio
import re
from fastapi import APIRouter, Depends, Request, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.logging_config import get_logger
from app.api.deps import get_current_user
from app.schemas.chat import ChatRequest, ChatResponse
from app.services import order_service

logger = get_logger(__name__)

router = APIRouter()


def _format_cart(cart: list[dict]) -> str:
    """格式化购物车文本。"""
    if not cart:
        return "当前购物车为空。"
    total = sum(float(c.get("unit_price", 0) or 0) * int(c.get("quantity", 1)) for c in cart)
    lines = [f"{c['name']} x{c['quantity']}" for c in cart]
    return f"当前购物车：{'、'.join(lines)}\n合计：¥{total:.2f}"


async def _process_chat(
    db: AsyncSession,
    user_id: int,
    message: str,
    cart: list[dict],
) -> dict:
    """
    基于规则的聊天处理。
    仅识别：确认下单、查看购物车、清空购物车、其他兜底回复。
    """
    text = message.strip()

    # 图片搜菜：直接提示已关闭
    if not text:
        return {
            "response": "您好，图片搜菜功能当前已关闭。",
            "cart": cart,
            "intent": "service",
            "agent": "fallback",
        }

    # 确认下单
    if re.search(r"确认下单|我要下单|下单|结账|付款|提交订单", text) and \
       not re.search(r"不要|别|先不|暂时不|千万别", text):
        if not cart:
            return {
                "response": "购物车为空，无法下单。请先添加菜品。",
                "cart": cart,
                "intent": "order",
                "agent": "fast_order",
            }
        try:
            response = await order_service.create_order_from_cart(db, user_id, cart)
            return {
                "response": response,
                "cart": [],  # 下单成功，清空购物车
                "intent": "order",
                "agent": "fast_order",
            }
        except Exception as e:
            logger.exception(f"[Chat] 下单失败: {e}")
            return {
                "response": f"下单失败：{str(e)}，请稍后重试或联系服务员。",
                "cart": cart,
                "intent": "order",
                "agent": "fast_order",
            }

    # 查看购物车
    if re.search(r"看看购物车|查看购物车|购物车|cart", text) and "清空" not in text:
        return {
            "response": _format_cart(cart),
            "cart": cart,
            "intent": "order",
            "agent": "fast_order",
        }

    # 清空购物车
    if re.search(r"清空购物车|清空|清除购物车|全删", text):
        return {
            "response": "购物车已清空。",
            "cart": [],
            "intent": "order",
            "agent": "fast_order",
        }

    # 兜底：返回引导语
    return {
        "response": (
            "您好！欢迎来到美味餐厅。\n"
            "您可以直接说：\n"
            "• 确认下单\n"
            "• 查看购物车\n"
            "• 清空购物车\n"
            "或前往菜单浏览菜品。"
        ),
        "cart": cart,
        "intent": "service",
        "agent": "fallback",
    }


@router.post("/chat", response_model=ChatResponse)
async def chat(
    request: Request,
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """聊天接口（同步 JSON 返回，向后兼容）"""
    user_id = current_user.get("id", data.user_id)
    try:
        result = await _process_chat(db, user_id, data.message, data.cart or [])
        return ChatResponse(
            response=result["response"],
            cart=result["cart"],
            intent=result.get("intent"),
            agent=result.get("agent"),
        )
    except Exception as e:
        logger.exception(f"[Chat] 处理失败: {e}")
        raise HTTPException(status_code=500, detail=f"服务异常: {str(e)}")


@router.post("/chat/stream")
async def chat_stream(
    request: Request,
    data: ChatRequest,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_user),
):
    """聊天接口（SSE 流式输出，向后兼容）"""
    user_id = current_user.get("id", data.user_id)

    async def event_generator():
        try:
            result = await _process_chat(db, user_id, data.message, data.cart or [])
            response_text = result.get("response", "")
            new_cart = result.get("cart", data.cart or [])

            # 逐字符 SSE 发送（打字机效果）
            for char in response_text:
                payload = json.dumps({"type": "text", "content": char}, ensure_ascii=False)
                yield f"data: {payload}\n\n"
                await asyncio.sleep(0.015)

            # 发送结束事件，附带 cart 数据
            done_payload = json.dumps({"type": "done", "cart": new_cart}, ensure_ascii=False)
            yield f"data: {done_payload}\n\n"

        except Exception as e:
            logger.exception(f"[ChatStream] 处理失败: {e}")
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
