"""v2.17.10 周期账单页顶栏不换行测试。

覆盖：recurring.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
周期账单页引用 recurring.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。
"""


async def test_recurring_topbar_single_line(client):
    """周期账单页顶栏导航应单行不换行（v2.17.9 只修了导入导出页，本轮补周期账单页）。"""
    response = await client.get("/static/recurring.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/recurring")
    assert page.status_code == 200
    html = page.text
    assert "/static/recurring.css" in html
    assert html.index("/static/style.css") < html.index("/static/recurring.css")
