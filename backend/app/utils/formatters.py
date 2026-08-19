"""
文本/时间格式化工具
"""
from datetime import datetime, timedelta
from typing import Optional

# 数据库（MySQL Docker 容器）存储的是 UTC 朴素时间，
# 约定：数据库配置不动，所有对外使用侧统一通过本函数转为东八区本地时间
LOCAL_TIME_OFFSET = timedelta(hours=8)


def utc_to_local(dt: Optional[datetime]) -> Optional[datetime]:
    """将数据库中的 UTC 朴素时间转为东八区本地朴素时间，None 原样返回"""
    if dt is None:
        return None
    return dt + LOCAL_TIME_OFFSET


def mask_username(username: str) -> str:
    """用户名脱敏：仅保留第一个字，其余用 * 代替，如 刘玄德 -> 刘**"""
    if not username:
        return username
    if len(username) == 1:
        return username
    return username[0] + "*" * (len(username) - 1)


def fmt_price(price) -> str:
    """价格显示：整数去掉小数部分（¥186 而非 ¥186.0）。"""
    p = float(price)
    return f"{p:.0f}" if p == int(p) else f"{p:.2f}"


def order_status_text(status: str) -> str:
    """订单状态转中文"""
    mapping = {
        "pending": "待确认",
        "confirmed": "已确认",
        "completed": "已完成",
        "cancelled": "已取消",
    }
    return mapping.get(status, status)
