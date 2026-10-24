from feedflow.dedup import simhash, tokenize


def test_separators_tokens_identical():
    assert tokenize("hello_world") == ["hello", "world"]
    assert tokenize("hello world") == ["hello", "world"]
    assert tokenize("hello-world") == ["hello", "world"]


def test_separators_simhash_identical():
    a = simhash("hello_world")
    b = simhash("hello world")
    c = simhash("hello-world")
    assert a == b
    assert b == c


def test_double_space_tokens():
    assert tokenize("a  b") == ["a", "b"]
    assert tokenize("a b") == ["a", "b"]
    assert tokenize("a   b") == ["a", "b"]
    assert tokenize("a\tb") == ["a", "b"]
    assert tokenize("a\nb") == ["a", "b"]
    assert tokenize("  a  b  ") == ["a", "b"]
    assert tokenize("") == []
    assert tokenize("   ") == []
    assert tokenize("!!!") == []
    assert tokenize("Hello, World!") == ["hello", "world"]
    assert tokenize("foo___bar") == ["foo", "bar"]
    assert tokenize("A1_b2-C3") == ["a1", "b2", "c3"]
    assert tokenize("hello__world") == tokenize("hello world")
