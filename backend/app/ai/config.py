"""
AI 模块配置

独立读取 AI 配置项，不修改传统后端的 core/config.py。

读取优先级：
1. backend/.env 文件中显式设置的值（部署时手动配置，优先生效）
2. 操作系统环境变量（本地开发兜底）

注意：.env 中的占位符（如 your-xxx-api-key-here）视为"未设置"，会继续回退。
"""
import os
from pathlib import Path

from dotenv import dotenv_values

# backend/.env（本文件位于 backend/app/ai/config.py，上三级为 backend/）
_BACKEND_DIR = Path(__file__).resolve().parents[2]
_ENV_VALUES = dotenv_values(_BACKEND_DIR / ".env")

# .env 中的占位符前缀，视为未设置
_PLACEHOLDER_PREFIXES = ("your-", "change-me", "change-in-production")


def _get_config(name: str, default: str = "") -> str:
    """按 .env -> 环境变量 的优先级读取配置，占位符视为未设置。"""
    file_value = (_ENV_VALUES.get(name) or "").strip()
    if file_value and not file_value.lower().startswith(_PLACEHOLDER_PREFIXES):
        return file_value
    return os.getenv(name, default).strip()


# 阿里云百炼（DashScope）大语言模型
BAILIAN_API_KEY = _get_config("DASHSCOPE_API_KEY")
BAILIAN_BASE_URL = _get_config(
    "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)
BAILIAN_LLM_MODEL = _get_config("BAILIAN_LLM_MODEL", "deepseek-v4-flash-0731")

# 智谱 AI（视觉 / 向量，后续图片搜菜与 RAG 使用）
ZHIPU_API_KEY = _get_config("ZHIPU_API_KEY")
ZHIPU_VISION_MODEL = _get_config("ZHIPU_VISION_MODEL", "glm-4v-flash")
ZHIPU_EMBEDDING_MODEL = _get_config("ZHIPU_EMBEDDING_MODEL", "embedding-3")
ZHIPU_EMBEDDING_DIMENSIONS = int(_get_config("ZHIPU_EMBEDDING_DIMENSIONS", "512"))
