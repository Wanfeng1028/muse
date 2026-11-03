"""v2.17.4 账户页顶栏不换行测试。

覆盖：accounts.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
账户页引用 accounts.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。
"""


async def test_accounts_topbar_single_line(client):
    """账户页顶栏导航应单行不换行（v2.17.3 只修了拍照记账页，本轮补账户页）。"""
    response = await client.get("/static/accounts.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/accounts")
    assert page.status_code == 200
    html = page.text
    assert "/static/accounts.css" in html
    assert html.index("/static/style.css") < html.index("/static/accounts.css")
