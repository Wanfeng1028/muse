from feedflow.dedup import tokenize


def test_single_cjk_kept():
    assert tokenize("好") == ["好"]


def test_mixed_short():
    assert tokenize("ab好") == ["ab", "好"]


def test_mixed_short_reversed():
    assert tokenize("好ab") == ["好", "ab"]
