"""v2.17.6 分类页顶栏不换行测试。

覆盖：categories.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
分类页引用 categories.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。
"""


async def test_categories_topbar_single_line(client):
    """分类页顶栏导航应单行不换行（v2.17.5 只修了预算页，本轮补分类页）。"""
    response = await client.get("/static/categories.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/categories")
    assert page.status_code == 200
    html = page.text
    assert "/static/categories.css" in html
    assert html.index("/static/style.css") < html.index("/static/categories.css")
