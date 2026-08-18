"""
订单 PDF 导出工具
使用 ReportLab 内置 CID 字体（STSong-Light）支持中文，无需额外字体文件。
"""
import io
from datetime import datetime
from typing import List, Dict, Any

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import cm
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.cidfonts import UnicodeCIDFont
from reportlab.platypus import (
    SimpleDocTemplate,
    Paragraph,
    Spacer,
    Table,
    TableStyle,
)

from app.utils.formatters import order_status_text

# 注册中文字体
pdfmetrics.registerFont(UnicodeCIDFont("STSong-Light"))
FONT_NAME = "STSong-Light"


def _ensure_style() -> ParagraphStyle:
    """确保段落样式使用中文"""
    return ParagraphStyle(
        name="Chinese",
        fontName=FONT_NAME,
        fontSize=10,
        leading=14,
        wordWrap="CJK",
    )


def _format_datetime(dt: Any) -> str:
    if not dt:
        return ""
    if isinstance(dt, datetime):
        return dt.strftime("%Y-%m-%d %H:%M")
    return str(dt)


def _items_text(items: List[Dict[str, Any]]) -> str:
    if not items:
        return "-"
    lines = []
    for item in items:
        name = item.get("name") or f"菜品#{item.get('menu_item_id', '')}"
        qty = item.get("quantity", 1)
        unit = item.get("unit_price", 0)
        lines.append(f"{name} x{qty} ({unit:.2f}元)")
    return "\n".join(lines)


def build_orders_pdf(
    orders: List[Dict[str, Any]],
    title: str = "订单列表",
    show_user_id: bool = True,
) -> bytes:
    """
    根据订单列表生成 PDF 字节流。

    Args:
        orders: 订单字典列表，每个字典包含 id/user_id/username/status/created_at/items/total_price 等字段。
        title: PDF 标题。
        show_user_id: 是否包含用户ID列（商家端导出为 True；用户端导出不展示用户ID）。

    Returns:
        PDF 文件字节流。
    """
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=A4,
        rightMargin=2 * cm,
        leftMargin=2 * cm,
        topMargin=2 * cm,
        bottomMargin=2 * cm,
    )

    styles = getSampleStyleSheet()
    title_style = ParagraphStyle(
        name="TitleCN",
        parent=styles["Title"],
        fontName=FONT_NAME,
        fontSize=18,
        leading=24,
        alignment=1,  # 居中
        spaceAfter=14,
    )

    normal_style = _ensure_style()

    story = [Paragraph(title, title_style), Spacer(1, 0.3 * cm)]

    if not orders:
        story.append(Paragraph("暂无订单数据", normal_style))
    else:
        # 表头（用户端导出不包含用户ID列）
        headers = ["订单号"]
        if show_user_id:
            headers.append("用户ID")
        headers += ["用户名", "状态", "下单时间", "菜品明细", "总价"]
        data = [[Paragraph(h, normal_style) for h in headers]]

        for order in orders:
            row = [Paragraph(str(order.get("id", "")), normal_style)]
            if show_user_id:
                row.append(Paragraph(str(order.get("user_id", "")), normal_style))
            row += [
                Paragraph(order.get("username") or "-", normal_style),  # 脱敏用户名，如 刘**
                Paragraph(order_status_text(order.get("status", "")), normal_style),
                Paragraph(_format_datetime(order.get("created_at")), normal_style),
                Paragraph(_items_text(order.get("items", [])), normal_style),
                Paragraph(f"{order.get('total_price', 0):.2f}元", normal_style),
            ]
            data.append(row)

        # A4 宽度约 21cm，减去左右边距各 2cm，可用约 17cm
        items_col = len(headers) - 2  # “菜品明细”列索引
        if show_user_id:
            col_widths = [1.2 * cm, 1.5 * cm, 2 * cm, 1.8 * cm, 3.3 * cm, 5.2 * cm, 2 * cm]
        else:
            col_widths = [1.2 * cm, 2 * cm, 1.8 * cm, 3.3 * cm, 6.7 * cm, 2 * cm]

        table = Table(data, colWidths=col_widths, repeatRows=1)
        table.setStyle(TableStyle([
            ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#f5f7fa")),
            ("TEXTCOLOR", (0, 0), (-1, 0), colors.black),
            ("ALIGN", (0, 0), (-1, -1), "CENTER"),
            ("ALIGN", (items_col, 1), (items_col, -1), "LEFT"),  # 菜品明细左对齐
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("FONTNAME", (0, 0), (-1, 0), FONT_NAME),
            ("FONTSIZE", (0, 0), (-1, 0), 10),
            ("FONTNAME", (0, 1), (-1, -1), FONT_NAME),
            ("FONTSIZE", (0, 1), (-1, -1), 9),
            ("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
            ("LEFTPADDING", (0, 0), (-1, -1), 6),
            ("RIGHTPADDING", (0, 0), (-1, -1), 6),
            ("TOPPADDING", (0, 0), (-1, -1), 6),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ]))
        story.append(table)

        # 汇总
        total = sum(o.get("total_price", 0) for o in orders)
        story.append(Spacer(1, 0.5 * cm))
        story.append(
            Paragraph(f"订单总数：{len(orders)}    合计金额：{total:.2f}元", normal_style)
        )

    doc.build(story)
    return buffer.getvalue()
