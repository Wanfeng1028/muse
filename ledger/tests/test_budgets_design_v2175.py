"""v2.17.5 预算页顶栏不换行测试。

覆盖：budgets.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
预算页引用 budgets.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。
"""


async def test_budgets_topbar_single_line(client):
    """预算页顶栏导航应单行不换行（v2.17.4 只修了账户页，本轮补预算页）。"""
    response = await client.get("/static/budgets.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/budgets")
    assert page.status_code == 200
    html = page.text
    assert "/static/budgets.css" in html
    assert html.index("/static/style.css") < html.index("/static/budgets.css")
