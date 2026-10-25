"""v2.17.14 对账工作台页顶栏不换行测试。

覆盖：workbench.css 含顶栏单行规则（flex-wrap: nowrap、链接 7px 8px/13px），
对账工作台页引用 workbench.css 且在 style.css 之后；括号平衡。仅断言结构，
不依赖具体种子数据。对账工作台页路由为 /workbench（main.py 实测）。
"""


async def test_workbench_topbar_single_line(client):
    """对账工作台页顶栏导航应单行不换行（v2.17.13 只补了账单导入向导页，本轮补对账工作台页）。"""
    response = await client.get("/static/workbench.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert ".topbar .nav" in css
    assert "flex-wrap: nowrap" in css
    assert ".topbar .nav a" in css
    assert "padding: 7px 8px" in css
    assert "font-size: 13px" in css
    page = await client.get("/workbench")
    assert page.status_code == 200
    html = page.text
    assert "/static/workbench.css" in html
    assert html.index("/static/style.css") < html.index("/static/workbench.css")
