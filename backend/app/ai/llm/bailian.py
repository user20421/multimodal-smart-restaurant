"""
阿里云百炼大语言模型客户端（LangChain ChatOpenAI 封装）

百炼提供 OpenAI 兼容接口，直接通过 base_url 接入。
"""
from langchain_openai import ChatOpenAI

from app.ai import config

# 智能点餐助手"小餐"的人设（图片搜菜分支使用）
SYSTEM_PROMPT = (
    "你是美味餐厅的智能点餐助手“小餐”，语气友好、回答简洁。"
    "你可以和顾客聊天、介绍川菜口味、推荐菜品。"
    "顾客可以直接在对话里让你加菜、减菜或下单（如“来两份宫保鸡丁”），"
    "请引导顾客用一句话说明菜名和数量。"
)


def get_chat_llm(streaming: bool = False) -> ChatOpenAI:
    """获取百炼对话模型实例（LangChain ChatOpenAI）。

    qwen3.7-flash 系列（当前 qwen3.7-flash-2026-07-15）是混合思考模型且默认开启
    思考：思考链输出在独立的 reasoning_content 字段（不混入 content、无泄漏），
    但实测（2026-08-20 探针）开启后输出 token 暴涨（51→885）且耗时增加数倍。
    聊天场景不需要思考链，通过 extra_body 显式关闭，响应更快更省。
    """
    return ChatOpenAI(
        model=config.BAILIAN_LLM_MODEL,
        api_key=config.BAILIAN_API_KEY,
        base_url=config.BAILIAN_BASE_URL,
        streaming=streaming,
        extra_body={"enable_thinking": False},
    )


def get_chat_llm_x(streaming: bool = False) -> ChatOpenAI:
    """获取百炼更强模型实例（"餐厅经理"混合意图专用，BAILIAN_LLM_MODEL_X）。

    与基础模型的差异：不传 enable_thinking。实测（2026-08-20 探针验证）当前
    qwen3.7-plus 是混合思考模型且默认开启思考，但与模型 A 不同——其思考链输出在
    独立的 reasoning_content 字段、绝不混入 content，无泄漏问题；经理节点做的是
    多工具编排规划，保留思考可保住任务拆解质量（实测 enable_thinking=false 后
    模型明显降智，简单比较题都会答错），故维持默认开启。
    若未来换成会泄漏思考链的模型，可仿照 get_chat_llm 在 extra_body 中处理。
    """
    return ChatOpenAI(
        model=config.BAILIAN_LLM_MODEL_X,
        api_key=config.BAILIAN_API_KEY,
        base_url=config.BAILIAN_BASE_URL,
        streaming=streaming,
    )
