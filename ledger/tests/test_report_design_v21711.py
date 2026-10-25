"""v2.17.11 月度报告页顶栏不换行测试。

覆盖：report.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
月度报告页引用 report.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。
"""


async def test_report_topbar_single_line(client):
    """月度报告页顶栏导航应单行不换行（v2.17.10 只修了周期账单页，本轮补月度报告页）。"""
    response = await client.get("/static/report.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/report")
    assert page.status_code == 200
    html = page.text
    assert "/static/report.css" in html
    assert html.index("/static/style.css") < html.index("/static/report.css")
