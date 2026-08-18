"""
图片搜菜服务

流程：
1. 智谱视觉模型（glm-4v-flash）描述图片并判断是否为菜品
2. 是菜品 -> 结合本店真实菜单（调传统后端 menu_service），由百炼大模型
   比对并列出店内有/相似的菜品；没有则明确告知"没找到"
3. 不是菜品 -> 返回固定提示语，引导重新上传
"""
import json
import re
from typing import Any, Dict, List

from langchain_core.messages import HumanMessage, SystemMessage
from sqlalchemy.ext.asyncio import AsyncSession

from app.ai.llm.bailian import SYSTEM_PROMPT
from app.ai.llm.zhipu import get_vision_llm
from app.core.logging_config import get_logger
from app.services import menu_service

logger = get_logger(__name__)

# 非菜品时的固定回复
NOT_FOOD_REPLY = "图片识别失败，请您重新上传一张清晰的菜品图片哦～"

# 视觉模型分析提示词：要求输出 JSON 便于程序解析
VISION_PROMPT = """请观察这张图片，完成两件事：
1. 用一两句话简单描述图片内容（主体、颜色、状态等）。
2. 判断图片主体是否是菜品/食物；如果是，给出1-3个可能的菜名。

请严格按以下 JSON 格式输出，不要输出任何其他内容：
{"is_food": true, "description": "图片内容描述", "guess_names": ["可能的菜名"]}
如果不是菜品/食物，则输出：{"is_food": false, "description": "图片内容描述", "guess_names": []}"""

_SPICY_TEXT = {0: "不辣", 1: "微辣", 2: "中辣", 3: "特辣"}


def _extract_json(text: str) -> Dict[str, Any]:
    """从模型输出中宽容地提取 JSON 对象。"""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("视觉模型输出中未找到 JSON")
    return json.loads(match.group(0))


async def analyze_food_image(image_base64: str) -> Dict[str, Any]:
    """调用视觉模型分析图片，返回 {is_food, description, guess_names}。"""
    llm = get_vision_llm()
    message = HumanMessage(content=[
        {"type": "image_url", "image_url": {"url": image_base64}},
        {"type": "text", "text": VISION_PROMPT},
    ])
    result = await llm.ainvoke([message])
    content = result.content
    if not isinstance(content, str):
        content = "".join(str(p) for p in content)

    try:
        data = _extract_json(content)
        return {
            "is_food": bool(data.get("is_food")),
            "description": str(data.get("description", "")),
            "guess_names": [str(n) for n in data.get("guess_names", [])],
        }
    except (ValueError, json.JSONDecodeError) as e:
        logger.warning(f"[图片搜菜] 视觉模型输出解析失败，按非菜品处理: {e}; 原文: {content[:200]}")
        return {"is_food": False, "description": content[:200], "guess_names": []}


async def build_answer_messages(
    db: AsyncSession,
    analysis: Dict[str, Any],
    user_text: str = "",
) -> List:
    """拉取本店真实菜单，构造给百炼大模型的比对回答消息。"""
    items = await menu_service.get_menu_items(db)

    menu_lines = []
    for it in items:
        spicy = _SPICY_TEXT.get(it.spicy_level, "未知")
        tags = f"，标签：{it.tags}" if it.tags else ""
        rec = "，招牌推荐" if it.is_recommended else ""
        menu_lines.append(f"- {it.name}（{it.price:.0f}元，{it.category}，{spicy}{tags}{rec}）")
    menu_text = "\n".join(menu_lines)

    guess = "、".join(analysis["guess_names"]) or "无"
    prompt = f"""顾客上传了一张图片，想在店里找这道菜。{('顾客留言：' + user_text) if user_text else ''}

【图片识别结果】{analysis['description']}
【视觉模型猜测的菜名】{guess}

【本店菜单】
{menu_text}

请根据以上信息回答顾客：
1. 先用一句话向顾客描述图片里是什么；
2. 如果图片中的菜品与本店菜单有相同或非常相似的，列出 1-3 道本店菜品（菜名、价格、一句话亮点）；
3. 如果图片是菜品但本店确实没有相同或相似的，明确告诉顾客"这道菜我们店暂时没有"，并可推荐 1-2 道口味相近的本店菜品。
语气友好简洁，不要提及"识别结果""JSON"等内部细节。"""

    return [
        SystemMessage(content=SYSTEM_PROMPT),
        HumanMessage(content=prompt),
    ]
