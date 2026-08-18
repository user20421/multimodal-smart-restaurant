"""
智谱视觉模型客户端（LangChain ChatOpenAI 封装）

智谱提供 OpenAI 兼容接口，GLM-4V-Flash 为免费视觉理解模型。
"""
from langchain_openai import ChatOpenAI

from app.ai import config

ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


def get_vision_llm() -> ChatOpenAI:
    """获取智谱视觉模型实例（glm-4v-flash）。"""
    return ChatOpenAI(
        model=config.ZHIPU_VISION_MODEL,
        api_key=config.ZHIPU_API_KEY,
        base_url=ZHIPU_BASE_URL,
    )
