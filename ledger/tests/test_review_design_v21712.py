"""v2.17.12 复核页顶栏不换行测试。

覆盖：review.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
复核页引用 review.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。复核页路由为 /bills/review（main.py 实测）。
"""


async def test_review_topbar_single_line(client):
    """复核页顶栏导航应单行不换行（v2.17.11 只修了月度报告页，本轮补复核页）。"""
    response = await client.get("/static/review.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/bills/review")
    assert page.status_code == 200
    html = page.text
    assert "/static/review.css" in html
    assert html.index("/static/style.css") < html.index("/static/review.css")
