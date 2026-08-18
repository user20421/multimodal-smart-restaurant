"""
阿里云百炼大语言模型客户端（LangChain ChatOpenAI 封装）

百炼提供 OpenAI 兼容接口，直接通过 base_url 接入。
"""
from langchain_openai import ChatOpenAI

from app.ai import config

# 智能点餐助手"小餐"的人设
SYSTEM_PROMPT = (
    "你是美味餐厅的智能点餐助手“小餐”，语气友好、回答简洁。"
    "你可以和顾客聊天、介绍川菜口味、推荐菜品。"
    "当前为初期版本，你还不能真正操作购物车或下单，"
    "如果顾客要求下单/查订单，请引导他前往菜单或购物车页面操作。"
)


def get_chat_llm(streaming: bool = False) -> ChatOpenAI:
    """获取百炼对话模型实例（LangChain ChatOpenAI）。

    deepseek-v4-flash 是混合思考模型且默认开启思考，思考过程可能泄漏到
    回复正文中（如 "（是的。）（输出。）" 这类内心独白），且显著增加耗时。
    聊天场景不需要思考链，通过 extra_body 显式关闭。
    """
    return ChatOpenAI(
        model=config.BAILIAN_LLM_MODEL,
        api_key=config.BAILIAN_API_KEY,
        base_url=config.BAILIAN_BASE_URL,
        streaming=streaming,
        extra_body={"enable_thinking": False},
    )
