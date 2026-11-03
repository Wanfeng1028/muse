"""match_best 调度深度测试：别名优先（alias-first）语义。

覆盖：
1. 别名命中时，即使存在高优先级正则规则，也返回 source=alias；
2. 别名 direction 不匹配时不命中（不因别名返回 alias 结果）；
3. 无别名时正常走规则链路。

纯单元测试，直接调用 ledger.matching.match_best，不启动 app、不 mock。
"""

import pytest

from ledger import matching


def R(id, kw, pt, cid, direction="any", priority=0, enabled=1):
    """构造一条规则 dict，字段名对齐 matching 内部使用的键名。"""
    return {
        "id": id,
        "keyword": kw,
        "pattern_type": pt,
        "category_id": cid,
        "direction": direction,
        "priority": priority,
        "is_enabled": enabled,
    }


def call(cp, summary, direction, rules, aliases=[], history=[]):
    """薄封装 match_best，固定 top_categories=[] 以隔离分类排序逻辑。"""
    return matching.match_best(
        cp,
        summary,
        direction,
        rules=rules,
        aliases=aliases,
        history=history,
        top_categories=[],
    )


@pytest.mark.asyncio
async def test_alias_beats_high_priority_regex_rule():
    """别名命中时，即便存在高优先级正则规则，也返回 source=alias 且取别名分类。

    别名指向 category_id=101，正则规则指向 category_id=999 且 priority 极高。
    预期：source == "alias"，category_id == 101。
    """
    aliases = [
        {"alias": "星巴克", "category_id": 101, "direction": "out"},
    ]
    rules = [
        R(1, "星巴克.*", "regex", 999, direction="any", priority=100),
    ]

    result = call(
        "星巴克",
        "星巴克消费",
        "out",
        rules,
        aliases=aliases,
    )

    assert result is not None
    assert result["source"] == "alias"
    assert result["category_id"] == 101


@pytest.mark.asyncio
async def test_alias_direction_mismatch_does_not_hit_alias():
    """别名 direction 不匹配时不命中别名分支。

    别名仅对 income 生效，而当前 direction 为 expense。
    预期：source 不为 "alias"；若无其它规则命中，则返回 None。
    """
    aliases = [
        {"alias": "星巴克", "category_id": 101, "direction": "in"},
    ]

    result = call(
        "星巴克",
        "星巴克消费",
        "out",
        rules=[],
        aliases=aliases,
    )

    assert result is None or result.get("source") != "alias"


@pytest.mark.asyncio
async def test_no_alias_falls_back_to_rule_chain():
    """无别名时走规则链路，命中正则规则并返回 source=rule。

    别名列表为空，唯一规则 keyword="星巴克" 指向 category_id=202。
    预期：source == "rule"，category_id == 202。
    """
    rules = [
        R(1, "星巴克", "keyword", 202, direction="any", priority=0),
    ]

    result = call(
        "星巴克",
        "星巴克消费",
        "out",
        rules,
        aliases=[],
    )

    assert result is not None
    assert result["source"] == "rule_keyword"
    assert result["category_id"] == 202
