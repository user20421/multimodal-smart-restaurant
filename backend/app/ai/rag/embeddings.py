"""
智谱 Embedding 模型封装（LangChain OpenAIEmbeddings）

智谱提供 OpenAI 兼容接口，embedding-3 模型，本项目统一使用 512 维。
"""
from langchain_openai import OpenAIEmbeddings

from app.ai import config

ZHIPU_BASE_URL = "https://open.bigmodel.cn/api/paas/v4"


def get_embeddings() -> OpenAIEmbeddings:
    """获取智谱向量模型实例（embedding-3，512 维）。"""
    return OpenAIEmbeddings(
        model=config.ZHIPU_EMBEDDING_MODEL,
        api_key=config.ZHIPU_API_KEY,
        base_url=ZHIPU_BASE_URL,
        dimensions=config.ZHIPU_EMBEDDING_DIMENSIONS,
    )
