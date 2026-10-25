"""v2.17.1 交易页顶栏不换行测试。

覆盖：transactions.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
且括号平衡。仅断言结构，不依赖具体种子数据。
"""


async def test_transactions_topbar_single_line(client):
    """交易页顶栏导航应单行不换行（v2.16.0 只修了仪表盘页，本轮补交易页）。"""
    response = await client.get("/static/transactions.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
