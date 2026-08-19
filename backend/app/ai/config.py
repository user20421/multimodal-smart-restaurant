"""
AI 模块配置

独立读取 AI 配置项，不修改传统后端的 core/config.py。

IS_SERVER=false（开发模式）：
- 大模型 API Key 只从【操作系统环境变量】读取，无默认值；
- MongoDB 使用代码内置的本地默认连接（无密码、默认端口）。

IS_SERVER=true（部署模式）：
- 大模型 API Key 只从【backend/.env】读取，无默认值；
- MongoDB 使用 .env 的 MONGODB_URL（含用户名/密码/端口）。

模型名称（型号）：无论开发还是部署，都只从【backend/.env】读取，无默认值。

取不到 API Key / 模型名称时不会报错，AI 对话由 router 返回友好兜底回复
（见 app/ai/fallback.py），传统点餐链路不受影响。
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


def _get_key(name: str) -> str:
    """读取 API Key（无默认值）：
    开发模式只读操作系统环境变量；部署模式只读 backend/.env（占位符视为未设置）。
    """
    if IS_SERVER:
        return _get_env_file_value(name)
    return os.getenv(name, "").strip()


def _get_env_file_value(name: str) -> str:
    """只从 backend/.env 读取（占位符视为未设置），无默认值。"""
    file_value = (_ENV_VALUES.get(name) or "").strip()
    if file_value and not file_value.lower().startswith(_PLACEHOLDER_PREFIXES):
        return file_value
    return ""


# 是否部署模式（false=开发；true=部署）
IS_SERVER = _get_config("IS_SERVER", "false").lower() in ("1", "true", "yes")

# 阿里云百炼（DashScope）大语言模型
BAILIAN_API_KEY = _get_key("DASHSCOPE_API_KEY")
BAILIAN_LLM_MODEL = _get_env_file_value("BAILIAN_LLM_MODEL")
BAILIAN_BASE_URL = _get_config(
    "BAILIAN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1"
)

# 智谱 AI（视觉 / 向量，图片搜菜与 RAG 使用）
ZHIPU_API_KEY = _get_key("ZHIPU_API_KEY")
ZHIPU_VISION_MODEL = _get_env_file_value("ZHIPU_VISION_MODEL")
ZHIPU_EMBEDDING_MODEL = _get_env_file_value("ZHIPU_EMBEDDING_MODEL")
ZHIPU_EMBEDDING_DIMENSIONS = int(_get_config("ZHIPU_EMBEDDING_DIMENSIONS", "512"))

# MongoDB（AI 聊天对话历史存储，独立于传统后端 MySQL）
# 开发模式强制使用本地默认连接；部署模式使用 .env 的 MONGODB_URL
MONGODB_URL = (
    _get_config("MONGODB_URL", "mongodb://localhost:27017")
    if IS_SERVER
    else "mongodb://localhost:27017"
)
MONGODB_DB = _get_config("MONGODB_DB", "meiwei_ai")
CHAT_HISTORY_LIMIT = int(_get_config("AI_CHAT_HISTORY_LIMIT", "10"))
