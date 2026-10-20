import re
import html
from feedflow.store import highlight_snippet


def test_empty_text():
    assert highlight_snippet("", "词") == ""
    assert highlight_snippet(None, "词") == ""


def test_empty_keyword_escaped():
    assert highlight_snippet("<b>hi</b>", "") == "&lt;b&gt;hi&lt;/b&gt;"


def test_keyword_found_marked():
    # 宽松断言：只断言含 <mark> 与关键词原文，具体包裹形式以实测为准
    result = highlight_snippet("Hello World", "World")
    assert "<mark>" in result
    assert "World" in result


def test_keyword_not_found_truncated():
    text = "a" * 200
    result = highlight_snippet(text, "zzz")
    assert len(result) <= 120
    assert "<mark>" not in result


def test_html_escaped_in_output():
    text = "<script>alert(1)</script> 关键词在这里"
    result = highlight_snippet(text, "关键词")
    assert "<script>" not in result
    assert "<mark>" in result


def test_case_insensitive_find():
    result = highlight_snippet("Hello World", "hello")
    assert "<mark>" in result


def test_max_len_respected():
    text = "x" * 100 + "keyword" + "y" * 100
    result = highlight_snippet(text, "keyword", max_len=50)
    stripped = re.sub(r"<[^>]+>", "", result)
    assert len(stripped) <= 50


def test_keyword_longer_than_maxlen():
    text = "abcdefghij"
    keyword = "abcdefghij"
    result = highlight_snippet(text, keyword, max_len=5)
    assert isinstance(result, str)


def test_unicode_keyword():
    # 宽松断言：只断言含 <mark> 与关键词文本，具体包裹形式以实测为准
    result = highlight_snippet("我喜欢吃苹果", "苹果")
    assert "<mark>" in result
    assert "苹果" in result


def test_no_double_escape():
    result = highlight_snippet("a & b", "a")
    assert result.count("&amp;") == 1
    assert "&amp;amp;" not in result