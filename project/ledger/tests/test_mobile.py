"""v2.3 移动端适配冒烟测试。

覆盖范围：
- 10 个页面路由的 200 / viewport / content-type 基础可用性（参数化）。
- 首页品牌区 SVG mark 替换 emoji。
- style.css 的移动端断点、触控目标规则与移动端规则插槽。
- 交易页 / 侦探队列页 / 预算页 / 仪表盘 的关键结构挂载点。

仅断言结构与标记，不依赖具体种子数据金额。
"""

import pytest

# 10 个已核验的页面路由（全部 response_class=HTMLResponse）
PAGE_ROUTES = [
    "/",
    "/transactions",
    "/currencies",
    "/accounts",
    "/categories",
    "/budgets",
    "/recurring",
    "/import",
    "/statement",
    "/detective",
]


@pytest.mark.parametrize("route", PAGE_ROUTES)
async def test_page_returns_html_with_viewport(client, route):
    """每个页面都应 200、返回 HTML、且带移动端 viewport meta。"""
    response = await client.get(route)
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]
    assert '<meta name="viewport"' in response.text


async def test_home_brand_mark_replaces_emoji(client):
    """首页品牌区用 SVG mark，emoji 已被移除。"""
    response = await client.get("/")
    assert response.status_code == 200
    assert "brand-mark" in response.text
    assert "💰" not in response.text


async def test_style_css_mobile_rules(client):
    """style.css 应包含移动端断点、触控目标规则与规则插槽。"""
    response = await client.get("/static/style.css")
    assert response.status_code == 200
    assert "@media (max-width: 768px)" in response.text
    assert "min-height: 44px" in response.text
    assert "__LEDGER_MOBILE_MORE__" in response.text


async def test_transactions_page_has_tx_body(client):
    """交易页应包含表格挂载点 tx-body。"""
    response = await client.get("/transactions")
    assert response.status_code == 200
    assert "tx-body" in response.text


async def test_detective_page_has_markers(client):
    """侦探队列页应包含 cardList 与 rulesCard 标记。"""
    response = await client.get("/detective")
    assert response.status_code == 200
    assert "cardList" in response.text
    assert "rulesCard" in response.text


async def test_budgets_page_has_markers(client):
    """预算页应包含 budget-list 与 b-form 标记。"""
    response = await client.get("/budgets")
    assert response.status_code == 200
    assert "budget-list" in response.text
    assert "b-form" in response.text


async def test_dashboard_page_has_markers(client):
    """仪表盘应包含 summary-cards 与 quick-link-grid 标记。"""
    response = await client.get("/")
    assert response.status_code == 200
    assert "summary-cards" in response.text
    assert "quick-link-grid" in response.text


# === 未做事项 ===
# - 未测试移动端交互行为（JS 折叠、抽屉等），无对应事实依据。
# - 未断言具体 CSS 属性值组合（如媒体查询内某选择器样式），仅按约定断言关键标记。
# - 未覆盖 /static 下除 style.css 之外的资源。
