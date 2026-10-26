"""
v2.17.18 仪表盘页顶栏单行测试。
覆盖 dashboard.css 顶栏单行规则与仪表盘页引用顺序；
仅断言结构，不依赖具体种子数据；仪表盘页路由为 /（main.py 实测）。
"""


async def test_dashboard_topbar_single_line(client):
    """
    v2.17.0-v2.17.14 各页顶栏单行系列已覆盖其余 14 页，本轮补仪表盘页这一最后一页。
    """
    # 1. 获取仪表盘 CSS 并验证基本结构
    resp = await client.get("/static/dashboard.css")
    assert resp.status_code == 200
    css_text = resp.text
    # 括号平衡检查
    assert css_text.count("{") == css_text.count("}")

    # 断言顶栏单行所需规则是否存在
    assert ".topbar .nav" in css_text
    assert "flex-wrap: nowrap" in css_text
    assert "overflow-x: auto" in css_text
    assert "scrollbar-width: none" in css_text

    assert ".topbar .nav a" in css_text
    assert "padding: 7px 8px" in css_text
    assert "font-size: 13px" in css_text
    assert "white-space: nowrap" in css_text

    # 2. 获取仪表盘页面并验证 CSS 链接顺序
    resp = await client.get("/")
    assert resp.status_code == 200
    html = resp.text
    assert "/static/dashboard.css" in html

    idx_style = html.index("/static/style.css")
    idx_dash = html.index("/static/dashboard.css")
    assert idx_style < idx_dash
