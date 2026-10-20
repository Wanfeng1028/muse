import pytest

from feedflow.dedup import tokenize, simhash


def test_fullwidth_en_tokens():
    assert tokenize("Ｐｙｔｈｏｎ３发布") == ["python3", "发布"]


def test_fullwidth_en_simhash():
    assert simhash("Ｐｙｔｈｏｎ") == simhash("python")


def test_fullwidth_digits():
    assert tokenize("２０２６年") == ["2026", "年"]
