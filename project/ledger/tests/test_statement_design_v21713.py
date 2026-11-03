"""v2.17.13 账单导入向导页顶栏不换行测试。

覆盖：statement.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
账单导入向导页引用 statement.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。账单导入向导页路由为 /statement（main.py 实测）。
"""


async def test_statement_topbar_single_line(client):
    """账单导入向导页顶栏导航应单行不换行（v2.17.12 只补了复核页，本轮补账单导入向导页）。"""
    response = await client.get("/static/statement.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/statement")
    assert page.status_code == 200
    html = page.text
    assert "/static/statement.css" in html
    assert html.index("/static/style.css") < html.index("/static/statement.css")
