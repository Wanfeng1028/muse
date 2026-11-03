from ledger.matching import fuzzy_match_detail, fuzzy_rule_matches


def test_exact_substring():
    # 1. 子串命中：pattern "美团" 在 "美团外卖" 中，distance 0、window "美团"、matched True。
    p, h = "美团", "美团外卖"
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is True
    assert res["distance"] == 0
    assert res["window"] == "美团"

def test_one_char_diff_hit_3char():
    # 2. 1 字之差命中（3 字词）：pattern "星巴克" 对 "星巴客咖啡"，distance 1、matched True；
    # window 为首次取到最小距离的窗口 "星巴"
    p, h = "星巴克", "星巴客咖啡"
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is True
    assert res["distance"] == 1
    assert res["window"] == "星巴"

def test_two_char_pattern_one_diff_miss():
    # 3. 2 字词 1 字之差不命中：pattern "美团" 对 "美圆外卖"，distance 1、window "美"，
    # matched False（锁定 distance * 2 < len(pattern) 规则）
    p, h = "美团", "美圆外卖"
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is False
    assert res["distance"] == 1
    assert res["window"] == "美"

def test_long_pattern_two_diff_hit():
    # 4. 长词 2 字之差命中：构造 5 字 pattern "肯德基套餐" 与 haystack "肯得基套"，
    # 保证 distance 2 且 distance * 2 < 5，matched True
    p, h = "肯德基套餐", "肯得基套"
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is True
    assert res["distance"] == 2
    assert res["window"] == "肯得基套"

def test_long_word_over_threshold_miss():
    # 5. 长词超阈值不命中：pattern "肯德基" 对完全无关长串，matched False 且 distance 为求得的最小距离（int，不为 None）
    p, h = "肯德基", "麦当劳汉堡包"
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is False
    assert isinstance(res["distance"], int)
    assert res["distance"] > 0

def test_empty_pattern():
    # 6. 空 pattern 返回全 None 语义且 matched 为 False
    p, h = "", "美团"
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is False
    assert res["distance"] is None
    assert res["window"] is None
    assert res["threshold"] is None

def test_empty_haystack():
    # 6. 空 haystack 返回全 None 语义且 matched 为 False
    p, h = "美团", ""
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is False
    assert res["distance"] is None
    assert res["window"] is None
    assert res["threshold"] is None

def test_single_char_pattern():
    # 6. 单字 pattern 返回全 None 语义且 matched 为 False
    p, h = "美", "美团"
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is False
    assert res["distance"] is None
    assert res["window"] is None
    assert res["threshold"] is None

def test_rule_matches_consistency():
    # 7. fuzzy_rule_matches 与 fuzzy_match_detail 的 matched 一致性：对 1/2/3/5 四组入参逐一断言两者 matched 相等
    params = [
        ("美团", "美团外卖"),
        ("星巴克", "星巴客咖啡"),
        ("美团", "美圆外卖"),
        ("肯德基", "麦当劳汉堡包"),
    ]
    for p, h in params:
        assert fuzzy_rule_matches(p, h) == fuzzy_match_detail(p, h)["matched"]

def test_return_keys():
    # 8. 返回键集合恰好等于 {"matched", "distance", "window", "threshold"}
    p, h = "美团", "美团外卖"
    res = fuzzy_match_detail(p, h)
    assert set(res.keys()) == {"matched", "distance", "window", "threshold"}

def test_threshold_boundary_5char():
    # 9. 阈值边界：5 字 pattern 的 threshold 为 2（用子串命中例断言 threshold == 2）
    p, h = "肯德基套餐", "肯德基套餐"
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is True
    assert res["threshold"] == 2

def test_threshold_boundary_4char():
    # 9. 阈值边界：4 字 pattern 的 threshold 为 1（子串命中例断言 threshold == 1）
    p, h = "肯德基店", "肯德基店"
    res = fuzzy_match_detail(p, h)
    assert res["matched"] is True
    assert res["threshold"] == 1
