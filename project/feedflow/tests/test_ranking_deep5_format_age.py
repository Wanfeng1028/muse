from feedflow.ranking import _format_age


def test_format_age_minutes():
    assert _format_age(0.0) == "刚刚"
    assert _format_age(0.5) == "30 分钟前"
    assert _format_age(0.99) == "59 分钟前"


def test_format_age_hours_days():
    assert _format_age(1.0) == "1 小时前"
    assert _format_age(47.9) == "47 小时前"
    assert _format_age(48.0) == "2 天前"
    assert _format_age(72.5) == "3 天前"
