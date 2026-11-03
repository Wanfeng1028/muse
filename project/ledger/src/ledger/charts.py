"""轻量 SVG 图表生成（纯标准库）。

提供两张图：
- trend_svg：分组柱状图，展示近 N 个月的收入 / 支出趋势。
- hbars_svg：横向条形图，展示支出分类占比。

约定金额单位均为「分」（cents），仅在渲染时换算为「元」或「万」。
所有文本都经过 html.escape 处理，避免注入 / 特殊字符破坏 SVG。
"""

from __future__ import annotations

import html
from typing import Any

# 颜色常量
_INCOME_COLOR = "#3b82f6"
_EXPENSE_COLOR = "#ef4444"

# 字体（系统字体栈，无第三方依赖）
_FONT = "system-ui, -apple-system, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif"


def _esc(text: Any) -> str:
    """转义文本，供 SVG 内容安全使用。"""
    return html.escape(str(text), quote=True)


def _fmt_wan(cents: int) -> str:
    """分 -> 万元字符串，保留一位小数，去掉多余的 .0。"""
    wan = cents / 100.0 / 10000.0
    text = f"{wan:.1f}"
    if text.endswith(".0"):
        text = text[:-2]
    return text + "万"


def _fmt_yuan(cents: int) -> str:
    """分 -> 元字符串，千分位，保留两位小数。"""
    yuan = cents / 100.0
    return f"{yuan:,.2f}"


def _nice_max(value: float) -> float:
    """把一个最大值向上取整到「好看」的刻度值（1/2/5 * 10^n）。"""
    if value <= 0:
        return 1.0
    import math

    exp = math.floor(math.log10(value))
    base = 10**exp
    frac = value / base
    if frac <= 1:
        nice = 1
    elif frac <= 2:
        nice = 2
    elif frac <= 5:
        nice = 5
    else:
        nice = 10
    return nice * base


def _empty_svg(width: int, height: int, message: str = "暂无数据") -> str:
    """无数据时的占位 SVG。"""
    return (
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{_FONT}">'
        f'<rect width="{width}" height="{height}" fill="#ffffff"/>'
        f'<text x="{width / 2}" y="{height / 2}" text-anchor="middle" '
        f'dominant-baseline="middle" fill="#9ca3af" font-size="16">'
        f"{_esc(message)}</text>"
        f"</svg>"
    )


def trend_svg(points: list[dict], width: int = 720, height: int = 260) -> str:
    """近 N 个月收支趋势（分组柱状图）。

    points: [{"month": "YYYY-MM", "income_cents": n, "expense_cents": n}, ...]
    """
    if not points:
        return _empty_svg(width, height)

    # 布局参数
    pad_left = 60
    pad_right = 20
    pad_top = 48
    pad_bottom = 40
    plot_w = width - pad_left - pad_right
    plot_h = height - pad_top - pad_bottom

    # 数据与刻度
    values = [max(int(p.get("income_cents", 0)), int(p.get("expense_cents", 0))) for p in points]
    y_max_cents = _nice_max(max(values) if values else 0)
    # 每根柱子所属的「组」宽度
    n = len(points)
    group_w = plot_w / n
    bar_w = min(group_w * 0.32, 26.0)
    gap = min(group_w * 0.06, 6.0)

    def y_of(cents: float) -> float:
        return pad_top + plot_h - (cents / y_max_cents) * plot_h

    # 组装 SVG 片段
    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{_FONT}">'
    )
    # 背景
    parts.append(f'<rect width="{width}" height="{height}" fill="#ffffff"/>')
    # 标题
    parts.append(
        f'<text x="{width / 2}" y="26" text-anchor="middle" '
        f'fill="#111827" font-size="16" font-weight="600">'
        f"近 {n} 个月收支趋势</text>"
    )
    # 图例
    legend_y = 40
    parts.append(
        f'<rect x="{pad_left}" y="{legend_y - 8}" width="10" height="10" '
        f'rx="2" fill="{_INCOME_COLOR}"/>'
        f'<text x="{pad_left + 16}" y="{legend_y + 1}" fill="#374151" '
        f'font-size="12">收入</text>'
    )
    parts.append(
        f'<rect x="{pad_left + 70}" y="{legend_y - 8}" width="10" height="10" '
        f'rx="2" fill="{_EXPENSE_COLOR}"/>'
        f'<text x="{pad_left + 86}" y="{legend_y + 1}" fill="#374151" '
        f'font-size="12">支出</text>'
    )

    # y 轴刻度（4 段，含 0 与最大值）
    ticks = 4
    for i in range(ticks + 1):
        cents = y_max_cents * i / ticks
        y = y_of(cents)
        parts.append(
            f'<line x1="{pad_left}" y1="{y:.2f}" x2="{pad_left + plot_w:.2f}" '
            f'y2="{y:.2f}" stroke="#e5e7eb" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_left - 8}" y="{y + 4:.2f}" text-anchor="end" '
            f'fill="#6b7280" font-size="11">{_esc(_fmt_wan(int(cents)))}</text>'
        )

    # 柱子
    for idx, p in enumerate(points):
        cx = pad_left + group_w * (idx + 0.5)
        income = int(p.get("income_cents", 0))
        expense = int(p.get("expense_cents", 0))

        # 收入柱（偏左）
        x_in = cx - gap / 2 - bar_w
        y_in = y_of(income)
        h_in = pad_top + plot_h - y_in
        if h_in > 0:
            parts.append(
                f'<rect x="{x_in:.2f}" y="{y_in:.2f}" width="{bar_w:.2f}" '
                f'height="{h_in:.2f}" rx="2" fill="{_INCOME_COLOR}"/>'
            )

        # 支出柱（偏右）
        x_ex = cx + gap / 2
        y_ex = y_of(expense)
        h_ex = pad_top + plot_h - y_ex
        if h_ex > 0:
            parts.append(
                f'<rect x="{x_ex:.2f}" y="{y_ex:.2f}" width="{bar_w:.2f}" '
                f'height="{h_ex:.2f}" rx="2" fill="{_EXPENSE_COLOR}"/>'
            )

        # x 轴标签：只显示 MM 月
        month = str(p.get("month", ""))
        label = month[5:7] + "月" if len(month) >= 7 else month
        parts.append(
            f'<text x="{cx:.2f}" y="{pad_top + plot_h + 18:.2f}" '
            f'text-anchor="middle" fill="#6b7280" font-size="11">'
            f"{_esc(label)}</text>"
        )

    # 坐标轴
    parts.append(
        f'<line x1="{pad_left}" y1="{pad_top + plot_h}" '
        f'x2="{pad_left + plot_w}" y2="{pad_top + plot_h}" '
        f'stroke="#9ca3af" stroke-width="1"/>'
    )

    parts.append("</svg>")
    return "".join(parts)


def hbars_svg(items: list[dict], width: int = 720, row_h: int = 34) -> str:
    """支出分类占比（横向条形图）。

    items: [{"name": str, "color": str, "total_cents": int, "pct": float}, ...]
    """
    if not items:
        return _empty_svg(width, row_h * 3 + 48)

    # 布局参数
    pad_left = 16
    pad_right = 16
    pad_top = 48
    pad_bottom = 12

    name_w = 90  # 名称列宽
    bar_gap = 12  # 名称与条形之间的间距
    amount_w = 140  # 右侧金额 + 百分比列宽

    bar_x = pad_left + name_w + bar_gap
    bar_max_w = width - bar_x - amount_w - pad_right
    if bar_max_w < 40:
        bar_max_w = 40

    height = pad_top + row_h * len(items) + pad_bottom

    # 等比基准
    max_total = max(int(it.get("total_cents", 0)) for it in items) or 1

    parts: list[str] = []
    parts.append(
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}" font-family="{_FONT}">'
    )
    parts.append(f'<rect width="{width}" height="{height}" fill="#ffffff"/>')
    # 标题
    parts.append(
        f'<text x="{width / 2}" y="26" text-anchor="middle" '
        f'fill="#111827" font-size="16" font-weight="600">支出分类占比</text>'
    )

    # 逐行绘制
    for idx, it in enumerate(items):
        y = pad_top + idx * row_h
        mid = y + row_h / 2

        name = str(it.get("name", ""))
        color = str(it.get("color") or "#9ca3af")
        total = int(it.get("total_cents", 0))
        try:
            pct = float(it.get("pct", 0.0))
        except (TypeError, ValueError):
            pct = 0.0

        # 名称：超长截断（按字符数近似）
        max_chars = 6
        disp_name = name if len(name) <= max_chars else name[: max_chars - 1] + "…"
        parts.append(
            f'<text x="{pad_left + name_w}" y="{mid + 4:.2f}" text-anchor="end" '
            f'fill="#374151" font-size="13">{_esc(disp_name)}</text>'
        )

        # 条形背景
        bar_h = min(18, row_h - 14)
        bar_y = mid - bar_h / 2
        parts.append(
            f'<rect x="{bar_x:.2f}" y="{bar_y:.2f}" width="{bar_max_w:.2f}" '
            f'height="{bar_h:.2f}" rx="3" fill="#f3f4f6"/>'
        )

        # 条形本体（按最大值等比）
        w = bar_max_w * (total / max_total) if max_total > 0 else 0.0
        if w > 0:
            parts.append(
                f'<rect x="{bar_x:.2f}" y="{bar_y:.2f}" width="{w:.2f}" '
                f'height="{bar_h:.2f}" rx="3" fill="{_esc(color)}"/>'
            )

        # 右侧金额 + 百分比
        amount_text = f"{_fmt_yuan(total)} 元"
        pct_text = f"{pct:.1f}%"
        right_x = width - pad_right
        parts.append(
            f'<text x="{right_x:.2f}" y="{mid + 4:.2f}" text-anchor="end" '
            f'fill="#111827" font-size="13">'
            f"{_esc(amount_text)}</text>"
        )
        parts.append(
            f'<text x="{right_x - 110:.2f}" y="{mid + 4:.2f}" text-anchor="end" '
            f'fill="#6b7280" font-size="12">{_esc(pct_text)}</text>'
        )

    parts.append("</svg>")
    return "".join(parts)
