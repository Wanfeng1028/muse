
from feedflow import dedup


def test_tokenize_空与None返回空列表():
    assert dedup.tokenize("") == []
    assert dedup.tokenize(None) == []


def test_tokenize_纯英文小写合并():
    assert dedup.tokenize("Hello WORLD") == ["hello", "world"]


def test_tokenize_英文数字连写():
    assert dedup.tokenize("abc123") == ["abc123"]


def test_tokenize_全角数字归一化():
    assert dedup.tokenize("１２３") == ["123"]


def test_tokenize_中英混合顺序():
    assert dedup.tokenize("AI大模型") == ["ai", "大模", "模型"]


def test_tokenize_单字保留():
    assert dedup.tokenize("好") == ["好"]


def test_tokenize_标点分隔():
    assert dedup.tokenize("你好，世界") == ["你好", "世界"]


def test_simhash_确定性():
    result1 = dedup.simhash("人工智能大模型发展迅速")
    result2 = dedup.simhash("人工智能大模型发展迅速")
    assert result1 == result2
    assert len(result1) == 16
    assert all(c in "0123456789abcdef" for c in result1)


def test_simhash_词序无关():
    assert dedup.simhash("苹果 香蕉") == dedup.simhash("香蕉 苹果")


def test_get_text_for_标题加权两次():
    d = {"title": "T", "content_text": "C"}
    assert dedup.get_text_for(d) == "T T C"
    assert dedup.get_text_for({}) == ""
    assert dedup.get_text_for(None) == ""
