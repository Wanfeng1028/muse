
from feedflow.dedup import _is_cjk, tokenize


def test_exta_is_cjk():
    assert _is_cjk("\u3400") is True


def test_exta_bigram():
    assert tokenize("\u3400好") == ["\u3400好"]


def test_exta_single():
    assert tokenize("\u3400") == ["\u3400"]
