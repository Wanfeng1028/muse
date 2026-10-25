"""v2.17.8 侦探队列页顶栏不换行测试。

覆盖：detective.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
侦探队列页引用 detective.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。
"""


async def test_detective_topbar_single_line(client):
    """侦探队列页顶栏导航应单行不换行（v2.17.7 只修了汇率页，本轮补侦探队列页）。"""
    response = await client.get("/static/detective.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/detective")
    assert page.status_code == 200
    html = page.text
    assert "/static/detective.css" in html
    assert html.index("/static/style.css") < html.index("/static/detective.css")
