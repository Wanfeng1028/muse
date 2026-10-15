# tests/test_matching.py
"""匹配与指纹模块单元测试：normalize / fingerprint / 规则匹配 / 历史匹配 / 候选推荐 / 转账识别。"""
import hashlib

from ledger.matching import (  # type: ignore
    detect_transfer,
    fingerprint,
    match_by_history,
    match_by_rules,
    normalize,
    suggest_candidates,
)


class TestNormalize:
    """normalize：去空白/标点、ASCII 小写。"""

    def test_strips_whitespace_and_punctuation(self):
        """中英文标点与空白都应被剥离。"""
        assert normalize(" 支付宝 ，,。.  ") == "支付宝"

    def test_lowercases_ascii(self):
        """ASCII 字母统一小写。"""
        assert normalize("STARBUCKS Coffee") == "starbuckscoffee"

    def test_empty_string(self):
        """空串归一后仍是空串。"""
        assert normalize("") == ""


class TestFingerprint:
    """fingerprint：确定性 sha256 前 32 hex。"""

    def test_deterministic(self):
        """相同输入应产生相同指纹。"""
        args = ("2024-01-02", 123456, "out", "星巴克", "咖啡")
        assert fingerprint(*args) == fingerprint(*args)

    def test_hex_length(self):
        """指纹长度固定为 32。"""
        fp = fingerprint("2024-01-02", 1, "in", "a", "b")
        assert len(fp) == 32
        int(fp, 16)  # 必须是合法十六进制

    def test_case_normalized_in_counterparty(self):
        """counterparty 大小写差异应被归一化，指纹一致。"""
        a = fingerprint("2024-01-02", 1, "in", "Starbucks", "coffee")
        b = fingerprint("2024-01-02", 1, "in", "starbucks", "COFFEE")
        assert a == b

    def test_matches_manual_sha256(self):
        """与手工计算的 sha256 前 32 hex 一致。"""
        occurred_on, amount_cents, direction = "2024-01-02", 500, "out"
        counterparty, summary = "商户", "备注"
        # 实现只归一化 counterparty/summary，日期/金额/方向原样参与指纹
        key = "|".join(
            [occurred_on, str(amount_cents), direction, normalize(counterparty), normalize(summary)]
        )
        expected = hashlib.sha256(key.encode("utf-8")).hexdigest()[:32]
        assert fingerprint(occurred_on, amount_cents, direction, counterparty, summary) == expected


class TestMatchByRules:
    """match_by_rules：关键字命中，方向过滤，priority 与 keyword 长度决胜。"""

    def test_single_hit_returns_category_and_95(self):
        """单条命中返回 (category_id, 95)。"""
        rules = [{"keyword": "星巴克", "category_id": 7, "direction": "out", "priority": 1}]
        assert match_by_rules("星巴克", "咖啡", "out", rules) == (7, 95)

    def test_direction_filtered_out(self):
        """方向不匹配时不应命中。"""
        rules = [{"keyword": "星巴克", "category_id": 7, "direction": "in", "priority": 1}]
        assert match_by_rules("星巴克", "咖啡", "out", rules) is None

    def test_direction_any_wildcard(self):
        """direction=any 通配。"""
        rules = [{"keyword": "工资", "category_id": 3, "direction": "any", "priority": 1}]
        assert match_by_rules("工资", "工资", "in", rules) == (3, 95)

    def test_priority_wins(self):
        """多条命中取 priority 更大者。"""
        rules = [
            {"keyword": "咖啡", "category_id": 1, "direction": "out", "priority": 1},
            {"keyword": "咖啡", "category_id": 2, "direction": "out", "priority": 9},
        ]
        assert match_by_rules("星巴克咖啡", "咖啡", "out", rules) == (2, 95)

    def test_keyword_length_tiebreak(self):
        """priority 并列时取 keyword 更长者。"""
        rules = [
            {"keyword": "咖啡", "category_id": 1, "direction": "out", "priority": 5},
            {"keyword": "星巴克咖啡", "category_id": 2, "direction": "out", "priority": 5},
        ]
        assert match_by_rules("星巴克咖啡", "咖啡", "out", rules) == (2, 95)

    def test_empty_keyword_skipped(self):
        """空关键词应跳过，不误伤。"""
        rules = [{"keyword": "", "category_id": 1, "direction": "out", "priority": 99}]
        assert match_by_rules("任意", "任意", "out", rules) is None

    def test_no_rules_returns_none(self):
        """无规则返回 None。"""
        assert match_by_rules("星巴克", "咖啡", "out", []) is None


class TestMatchByHistory:
    """match_by_history：精确>=2 票、模糊>=2 票、方向一致。"""

    def test_exact_two_votes(self):
        """精确匹配 2 票，confidence=60+2*10=80。"""
        history = [
            {"counterparty": "星巴克", "summary": "咖啡", "category_id": 7, "direction": "out"},
            {"counterparty": "星巴克", "summary": "咖啡", "category_id": 7, "direction": "out"},
        ]
        assert match_by_history("星巴克", "咖啡", "out", history) == (7, 80)

    def test_exact_single_vote_not_enough(self):
        """精确匹配 1 票不算。"""
        history = [{"counterparty": "星巴克", "summary": "咖啡", "category_id": 7, "direction": "out"}]
        assert match_by_history("星巴克", "咖啡", "out", history) is None

    def test_confidence_capped_at_90(self):
        """票数很多时 confidence 上限 90。"""
        history = [
            {"counterparty": "星巴克", "summary": "咖啡", "category_id": 7, "direction": "out"}
            for _ in range(6)
        ]
        assert match_by_history("星巴克", "咖啡", "out", history) == (7, 90)

    def test_fuzzy_two_votes(self):
        """互包含且长度>=2，2 票，confidence=65。"""
        history = [
            {"counterparty": "星巴克咖啡", "summary": "拿铁", "category_id": 7, "direction": "out"},
            {"counterparty": "星巴克咖啡店", "summary": "拿铁", "category_id": 7, "direction": "out"},
        ]
        assert match_by_history("星巴克", "拿铁", "out", history) == (7, 65)

    def test_direction_mismatch_ignored(self):
        """方向不一致的条目不计票。"""
        history = [
            {"counterparty": "星巴克", "summary": "咖啡", "category_id": 7, "direction": "in"},
            {"counterparty": "星巴克", "summary": "咖啡", "category_id": 7, "direction": "in"},
        ]
        assert match_by_history("星巴克", "咖啡", "out", history) is None


class TestSuggestCandidates:
    """suggest_candidates：最多 3 条，confidence 按名次 55/45/35。"""

    def test_returns_at_most_three(self):
        """即使有更多历史也应最多返回 3 条。"""
        history = [
            {"counterparty": "星巴克", "summary": "咖啡", "category_id": 7, "direction": "out"}
            for _ in range(5)
        ]
        top = [(1, 9), (2, 8), (3, 7), (4, 6), (5, 5)]
        result = suggest_candidates("星巴克", "咖啡", "out", history, top)
        assert len(result) <= 3

    def test_confidence_by_rank(self):
        """confidence 依次为 55/45/35。"""
        history = []
        top = [(11, 9), (22, 8), (33, 7)]
        result = suggest_candidates("陌生商户", "陌生备注", "out", history, top)
        assert len(result) == 3
        assert [r[2] for r in result] == [55, 45, 35]

    def test_history_first_then_top(self):
        """历史命中应优先，top 分类补位。"""
        history = [
            {"counterparty": "星巴克", "summary": "咖啡", "category_id": 7, "direction": "out"},
            {"counterparty": "星巴克", "summary": "咖啡", "category_id": 7, "direction": "out"},
        ]
        top = [(7, 9), (8, 8), (9, 7)]
        result = suggest_candidates("星巴克", "咖啡", "out", history, top)
        assert result[0][0] == 7
        # 历史 category_id 不应重复出现在补位中
        ids = [r[0] for r in result]
        assert len(ids) == len(set(ids))

    def test_shape_triple(self):
        """返回三元组 (category_id, name, confidence)。"""
        result = suggest_candidates("x", "y", "out", [], [(5, 3)])
        assert len(result) == 1
        cid, name, conf = result[0]
        assert cid == 5
        assert isinstance(name, str)
        assert conf == 55


class TestDetectTransfer:
    """detect_transfer：精确/模糊命中账户名。"""

    def test_exact_match(self):
        """counterparty 与账户名精确匹配。"""
        accounts = {1: "招商银行储蓄卡", 2: "支付宝"}
        assert detect_transfer("支付宝", accounts) == 2

    def test_fuzzy_match(self):
        """counterparty 含账户名（互包含）应命中。"""
        accounts = {1: "招商银行储蓄卡"}
        assert detect_transfer("转账至招商银行储蓄卡", accounts) == 1

    def test_no_match(self):
        """无命中返回 None。"""
        accounts = {1: "招商银行储蓄卡"}
        assert detect_transfer("星巴克", accounts) is None
