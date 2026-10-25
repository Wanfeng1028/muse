"""v2.17.0 交易页设计层测试。

覆盖：交易页引用 transactions.css 且在 style.css 之后；
设计层可经 /static 取到、括号平衡、关键选择器齐全、无去 AI 味禁令串。
仅断言结构与标记，不依赖具体种子数据金额。
"""


async def test_transactions_page_references_design_layer_after_base(client):
    """交易页应 200，且先引 style.css、后引 transactions.css。"""
    response = await client.get("/transactions")
    assert response.status_code == 200
    assert "/static/transactions.css" in response.text
    assert response.text.index("/static/style.css") < response.text.index(
        "/static/transactions.css"
    )


async def test_transactions_design_layer_served_and_balanced(client):
    """设计层应可取到、括号平衡、含台账关键规则。"""
    response = await client.get("/static/transactions.css")
    assert response.status_code == 200
    css = response.text
    assert css.count("{") == css.count("}")
    assert css.count("{") >= 16
    for selector in (
        "main h1",
        ".filters #btn-search",
        "table thead th",
        "table tbody td:nth-child(5)",
        ".pagination",
        "#tx-form button",
    ):
        assert selector in css


async def test_transactions_design_layer_has_no_ai_slop_markers(client):
    """设计层规则体不得含紫渐变、毛玻璃、Inter 独占、!important。

    文件头自查注释会提到禁令词本身，故先剥注释再断言。
    """
    import re

    response = await client.get("/static/transactions.css")
    css = re.sub(r"/\*.*?\*/", "", response.text, flags=re.S)
    for banned in ("linear-gradient", "backdrop-filter", "Inter", "!important"):
        assert banned not in css
