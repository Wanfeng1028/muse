from datetime import date

from fastapi import HTTPException
import pytest

from ledger.routers.reports import (
    _validate_year_month,
    _prev_year_month,
    _month_range,
    _extract_merchant,
)


def test_validate_合法月份通过():
    assert _validate_year_month("2026-10") == "2026-10"
    assert _validate_year_month("2026-01") == "2026-01"


def test_validate_非法月份抛422():
    invalid_values = ["2026-13", "2026-00", "2026-1", "26-10", "2026/10", "2026-10-01", ""]
    for value in invalid_values:
        with pytest.raises(HTTPException) as excinfo:
            _validate_year_month(value)
        assert excinfo.value.status_code == 422
        assert excinfo.value.detail == "year_month 格式必须为 YYYY-MM"
    with pytest.raises(TypeError):
        _validate_year_month(None)


def test_prev_普通月份():
    assert _prev_year_month("2026-10") == "2026-09"
    assert _prev_year_month("2026-03") == "2026-02"


def test_prev_跨年():
    assert _prev_year_month("2026-01") == "2025-12"
    assert _prev_year_month("2000-01") == "1999-12"


def test_month_range_普通月():
    assert _month_range("2026-10") == ("2026-10-01", "2026-10-31")


def test_month_range_闰年2月():
    assert _month_range("2024-02") == ("2024-02-01", "2024-02-29")
    assert _month_range("2025-02") == ("2025-02-01", "2025-02-28")


def test_month_range_12月跨年():
    assert _month_range("2026-12") == ("2026-12-01", "2026-12-31")


def test_month_range_起止均为含端ISO串():
    start, end = _month_range("2026-10")
    assert len(start) == 10
    assert len(end) == 10
    date.fromisoformat(start)
    date.fromisoformat(end)
    assert start <= end


def test_extract_正常备注取首词():
    assert _extract_merchant("星巴克 臻选店 拿铁") == "星巴克"


def test_extract_空备注返回未备注():
    for value in [None, "", "   "]:
        assert _extract_merchant(value) == "未备注"


def test_extract_首尾空格被剥离():
    assert _extract_merchant("  海底捞 聚餐  ") == "海底捞"


def test_extract_无空格整个返回():
    assert _extract_merchant("蜜雪冰城") == "蜜雪冰城"
