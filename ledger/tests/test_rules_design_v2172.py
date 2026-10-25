"""v2.17.2 规则页顶栏不换行测试。

覆盖：rules.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
规则页引用 rules.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。
"""


async def test_rules_topbar_single_line(client):
    """规则页顶栏导航应单行不换行（v2.17.1 只修了交易页，本轮补规则页）。"""
    response = await client.get("/static/rules.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/rules")
    assert page.status_code == 200
    html = page.text
    assert "/static/rules.css" in html
    assert html.index("/static/style.css") < html.index("/static/rules.css")
