from __future__ import annotations

from ledger.matching import match_by_rules

# match_by_rules 的平局决胜：同 priority 且同归一化 keyword 长度时，保留先出现的规则，
# 因为它仅在 priority 更大 或 同 priority 且 keyword 更长 时才替换 best，
# 没有基于 id 的平局决胜。match_best 内部的 _pick_best_keyword 不同，同 priority 同长度取小 id，
# 两者行为存在差异。


def test_tie_first_wins() -> None:
    # 两条规则 priority 相同、归一化后 keyword 长度相同、都命中，先出现的胜出
    rules = [
        {"id": 11, "keyword": "咖啡", "category_id": 101, "direction": "any", "priority": 5, "is_enabled": 1},
        {"id": 22, "keyword": "奶茶", "category_id": 202, "direction": "any", "priority": 5, "is_enabled": 1},
    ]
    result = match_by_rules("咖啡奶茶店", "", "out", rules, include_rule_id=True)
    assert result == (101, 95, 11)


def test_tie_longer_keyword_wins() -> None:
    # 同 priority 但 keyword 更长的在后面，长度决胜与顺序无关
    rules = [
        {"id": 11, "keyword": "咖啡", "category_id": 101, "direction": "any", "priority": 5, "is_enabled": 1},
        {"id": 22, "keyword": "生椰咖啡", "category_id": 202, "direction": "any", "priority": 5, "is_enabled": 1},
    ]
    result = match_by_rules("生椰咖啡", "", "out", rules, include_rule_id=True)
    assert result == (202, 95, 22)


def test_higher_priority_later_wins() -> None:
    # priority 更高的在后面，高 priority 的胜出
    rules = [
        {"id": 11, "keyword": "打车", "category_id": 101, "direction": "any", "priority": 1, "is_enabled": 1},
        {"id": 22, "keyword": "打车", "category_id": 202, "direction": "any", "priority": 9, "is_enabled": 1},
    ]
    result = match_by_rules("打车回家", "", "out", rules, include_rule_id=True)
    assert result == (202, 95, 22)


def test_disabled_rule_skipped() -> None:
    # is_enabled=0 的规则即使命中也被跳过，只有启用的规则参与匹配
    rules = [
        {"id": 11, "keyword": "超市", "category_id": 101, "direction": "any", "priority": 9, "is_enabled": 0},
        {"id": 22, "keyword": "超市", "category_id": 202, "direction": "any", "priority": 1, "is_enabled": 1},
    ]
    result = match_by_rules("超市购物", "", "out", rules, include_rule_id=True)
    assert result == (202, 95, 22)
