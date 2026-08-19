"""
输出净化：确定性移除表情符号与舞台指示

提示词约束（"不使用表情符号"）并非 100% 可靠，这里在出口处做确定性兜底，
保证对话中不出现表情。注意：只匹配 emoji 区间，不影响中文与常规标点。
"""
import re

_EMOJI_RE = re.compile(
    "["
    "\U0001f000-\U0001faff"  # 各类表情符号与象形文字
    "\U00002600-\U000027bf"  # 杂项符号 / 装饰符号
    "\U00002b00-\U00002bff"  # 杂项符号与箭头
    "\U0001f1e6-\U0001f1ff"  # 旗帜（区域指示符）
    "\ufe0f"                 # 变体选择符-16（emoji 呈现）
    "\u200d"                 # 零宽连接符（组合 emoji）
    "]",
    flags=re.UNICODE,
)

# 舞台指示/语气动作标注（如“（微笑）”“(点头)”）：括号内只含此类词时整体移除，
# 含其他内容的正常括号（如“（已确认）”“（微辣）”）不受影响
_STAGE_WORDS = (
    "微笑|轻笑|大笑|笑|点头|摇头|眨眼|叹气|皱眉|鼓掌|挥手|害羞|"
    "调皮|得意|温柔|开心|难过|生气|语气轻快|停顿|思考|认真"
)
_STAGE_DIRECTION_RE = re.compile(
    rf"\s*[（(](?:{_STAGE_WORDS})(?:[，、,~～\s]*(?:{_STAGE_WORDS}))*[）)]"
)


def strip_emoji(text: str) -> str:
    """移除文本中的表情符号，其余内容原样保留。"""
    if not text:
        return text
    return _EMOJI_RE.sub("", text)


def strip_stage_directions(text: str) -> str:
    """移除“（微笑）”这类舞台指示/语气动作标注。"""
    if not text:
        return text
    return _STAGE_DIRECTION_RE.sub("", text)


def sanitize_reply(text: str) -> str:
    """回复出口净化：表情符号 + 舞台指示标注。"""
    return strip_stage_directions(strip_emoji(text))
