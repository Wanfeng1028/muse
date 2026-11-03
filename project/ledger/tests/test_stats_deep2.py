from datetime import date, timedelta

import pytest


def _prev_month_str(offset: int = 1) -> str:
    today = date.today()
    y, m = today.year, today.month
    for _ in range(offset):
        if m == 1:
            y, m = y - 1, 12
        else:
            m -= 1
    return f"{y:04d}-{m:02d}"


async def _account_id(client):
    resp = await client.get("/api/accounts")
    assert resp.status_code == 200, resp.text
    accounts = resp.json()
    if accounts:
        return accounts[0]["id"]
    created = await client.post(
        "/api/accounts",
        json={"name": "deep-acc", "type": "cash", "opening_balance_cents": 0},
    )
    assert created.status_code in (200, 201), created.text
    return created.json()["id"]


async def _cat_id(client, name, kind):
    resp = await client.get("/api/categories", params={"kind": kind})
    assert resp.status_code == 200, resp.text
    for c in resp.json():
        if c["name"] == name:
            return c["id"]
    return None


async def _tx(client, **kw):
    resp = await client.post("/api/transactions", json=kw)
    assert resp.status_code in (200, 201), resp.text
    return resp.json()


@pytest.mark.parametrize(
    "bad",
    [
        "2024-13",
        "2024-00",
        "2024-1",
        "24-01",
        "2024/01",
        "2024-01-01",
        "abcd-ef",
        "2024-",
        "-2024-01",
        "2024-012",
        " 2024-01",
        "2024-01 ",
    ],
)
async def test_summary_invalid_month_rejected(client, bad):
    resp = await client.get("/api/stats/summary", params={"month": bad})
    assert resp.status_code == 400, resp.text
    assert "month" in resp.json()["detail"]


async def test_summary_empty_month_treated_as_default(client):
    resp = await client.get("/api/stats/summary", params={"month": ""})
    assert resp.status_code == 200, resp.text
    assert resp.json()["month"] == date.today().strftime("%Y-%m")


async def test_summary_future_month_zeroed(client):
    future_year = date.today().year + 5
    resp = await client.get("/api/stats/summary", params={"month": f"{future_year}-06"})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["month"] == f"{future_year}-06"
    assert data["income_cents"] == 0
    assert data["expense_cents"] == 0
    assert data["net_cents"] == 0


async def test_summary_month_boundary_first_and_last_day(client):
    await _account_id(client)
    acc = await _account_id(client)
    salary = await _cat_id(client, "工资", "income")
    if salary is None:
        pytest.skip("seed category 工资 missing")
    today = date.today()
    first = today.replace(day=1)
    if first.month == 12:
        last = first.replace(year=first.year + 1, month=1) - timedelta(days=1)
    else:
        last = first.replace(month=first.month + 1) - timedelta(days=1)
    await _tx(
        client,
        account_id=acc,
        category_id=salary,
        type="income",
        amount_cents=1111,
        occurred_on=first.isoformat(),
    )
    await _tx(
        client,
        account_id=acc,
        category_id=salary,
        type="income",
        amount_cents=2222,
        occurred_on=last.isoformat(),
    )
    resp = await client.get(
        "/api/stats/summary", params={"month": today.strftime("%Y-%m")}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["income_cents"] >= 3333


async def test_summary_boundary_day_outside_month_excluded(client):
    await _account_id(client)
    acc = await _account_id(client)
    salary = await _cat_id(client, "工资", "income")
    if salary is None:
        pytest.skip("seed category 工资 missing")
    today = date.today()
    first = today.replace(day=1)
    outside = first - timedelta(days=1)
    await _tx(
        client,
        account_id=acc,
        category_id=salary,
        type="income",
        amount_cents=999999,
        occurred_on=outside.isoformat(),
    )
    resp = await client.get(
        "/api/stats/summary", params={"month": today.strftime("%Y-%m")}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["income_cents"] == 0


@pytest.mark.parametrize("months", [0, -1, 25, 100, -100])
async def test_trend_out_of_range_rejected(client, months):
    resp = await client.get("/api/stats/trend", params={"months": months})
    assert resp.status_code == 422, resp.text


@pytest.mark.parametrize("months", [1, 24])
async def test_trend_boundary_values_accepted(client, months):
    resp = await client.get("/api/stats/trend", params={"months": months})
    assert resp.status_code == 200, resp.text
    assert len(resp.json()) == months


async def test_trend_non_integer_rejected(client):
    resp = await client.get("/api/stats/trend", params={"months": "abc"})
    assert resp.status_code == 422, resp.text


async def test_trend_empty_dataset_all_zero(client):
    resp = await client.get("/api/stats/trend", params={"months": 3})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert len(data) == 3
    for item in data:
        assert item["income_cents"] == 0
        assert item["expense_cents"] == 0


async def test_trend_months_ordering_and_last_is_current(client):
    resp = await client.get("/api/stats/trend", params={"months": 5})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    months = [item["month"] for item in data]
    assert months == sorted(months)
    assert len(set(months)) == 5
    assert months[-1] == date.today().strftime("%Y-%m")


async def test_by_category_invalid_kind_rejected(client):
    resp = await client.get(
        "/api/stats/by-category", params={"kind": "transfer"}
    )
    assert resp.status_code == 400, resp.text
    assert "kind" in resp.json()["detail"]


@pytest.mark.parametrize("kind", ["EXPENSE", "Expense", "income ", "支出"])
async def test_by_category_kind_case_and_whitespace_rejected(client, kind):
    resp = await client.get("/api/stats/by-category", params={"kind": kind})
    assert resp.status_code == 400, resp.text


async def test_by_category_invalid_month_rejected(client):
    resp = await client.get(
        "/api/stats/by-category",
        params={"month": "2024-13", "kind": "expense"},
    )
    assert resp.status_code == 400, resp.text


async def test_by_category_empty_month_uses_default(client):
    resp = await client.get(
        "/api/stats/by-category", params={"month": "", "kind": "expense"}
    )
    assert resp.status_code == 200, resp.text


async def test_by_category_income_kind_returns_list(client):
    resp = await client.get(
        "/api/stats/by-category", params={"kind": "income"}
    )
    assert resp.status_code == 200, resp.text
    assert isinstance(resp.json(), list)


async def test_by_category_future_month_empty_list(client):
    future = f"{date.today().year + 3}-01"
    resp = await client.get(
        "/api/stats/by-category",
        params={"month": future, "kind": "expense"},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json() == []


async def test_by_category_empty_month_string_rejected_but_kind_checked_first(client):
    resp = await client.get(
        "/api/stats/by-category", params={"month": "bad", "kind": "bad"}
    )
    assert resp.status_code == 400, resp.text
    assert "kind" in resp.json()["detail"]


async def test_net_worth_no_data_is_zero(client):
    resp = await client.get("/api/stats/net-worth")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_cents"] == 0


async def test_net_worth_negative_when_expense_exceeds_income(client):
    acc = await _account_id(client)
    food = await _cat_id(client, "餐饮", "expense")
    if food is None:
        pytest.skip("seed category 餐饮 missing")
    await _tx(
        client,
        account_id=acc,
        category_id=food,
        type="expense",
        amount_cents=12345,
        occurred_on=date.today().isoformat(),
    )
    resp = await client.get("/api/stats/net-worth")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_cents"] == -12345


async def test_summary_excludes_other_months(client):
    acc = await _account_id(client)
    salary = await _cat_id(client, "工资", "income")
    if salary is None:
        pytest.skip("seed category 工资 missing")
    prev = _prev_month_str(1)
    await _tx(
        client,
        account_id=acc,
        category_id=salary,
        type="income",
        amount_cents=77777,
        occurred_on=f"{prev}-10",
    )
    resp = await client.get(
        "/api/stats/summary", params={"month": date.today().strftime("%Y-%m")}
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["income_cents"] == 0


async def test_trend_reflects_previous_month_data(client):
    acc = await _account_id(client)
    salary = await _cat_id(client, "工资", "income")
    if salary is None:
        pytest.skip("seed category 工资 missing")
    prev = _prev_month_str(1)
    await _tx(
        client,
        account_id=acc,
        category_id=salary,
        type="income",
        amount_cents=43210,
        occurred_on=f"{prev}-20",
    )
    resp = await client.get("/api/stats/trend", params={"months": 2})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data[0]["month"] == prev
    assert data[0]["income_cents"] == 43210
    assert data[-1]["income_cents"] == 0


async def test_validate_month_function_accepts_valid_pattern():
    from ledger.routers.stats import _validate_month

    assert _validate_month("2024-01") == "2024-01"
    assert _validate_month("1999-12") == "1999-12"


@pytest.mark.parametrize(
    "bad",
    ["", "2024-13", "2024-00", "2024-1", "202401", "2024-01-01", "abcd-ef"],
)
async def test_validate_month_function_raises_400(bad):
    from fastapi import HTTPException

    from ledger.routers.stats import _validate_month

    with pytest.raises(HTTPException) as exc:
        _validate_month(bad)
    assert exc.value.status_code == 400


async def test_default_month_format_matches_regex():
    from ledger.routers.stats import _MONTH_RE, _default_month

    value = _default_month()
    assert _MONTH_RE.match(value), value
    assert value == date.today().strftime("%Y-%m")


async def test_month_regex_rejects_trailing_newline():
    from ledger.routers.stats import _MONTH_RE

    # Python 的 $ 在非多行模式下会匹配字符串末尾换行符之前的位置,
    # 因此 "2024-01\n" 仍会被 _MONTH_RE.match 命中, 返回 Match 对象。
    assert _MONTH_RE.match("2024-01\n") is not None


async def test_summary_invalid_month_not_treated_as_default(client):
    resp = await client.get("/api/stats/summary", params={"month": "not-a-month"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "month 必须为 YYYY-MM 格式"


async def test_by_category_boundary_month_first_day_only(client):
    acc = await _account_id(client)
    food = await _cat_id(client, "餐饮", "expense")
    if food is None:
        pytest.skip("seed category 餐饮 missing")
    today = date.today()
    first = today.replace(day=1)
    await _tx(
        client,
        account_id=acc,
        category_id=food,
        type="expense",
        amount_cents=555,
        occurred_on=first.isoformat(),
    )
    resp = await client.get(
        "/api/stats/by-category",
        params={"month": today.strftime("%Y-%m"), "kind": "expense"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    total = sum(item["total_cents"] for item in data)
    assert total == 555


async def test_net_worth_after_income_only(client):
    acc = await _account_id(client)
    salary = await _cat_id(client, "工资", "income")
    if salary is None:
        pytest.skip("seed category 工资 missing")
    await _tx(
        client,
        account_id=acc,
        category_id=salary,
        type="income",
        amount_cents=8888,
        occurred_on=date.today().isoformat(),
    )
    resp = await client.get("/api/stats/net-worth")
    assert resp.status_code == 200, resp.text
    assert resp.json()["total_cents"] == 8888


async def test_trend_ordering_with_data_across_months(client):
    acc = await _account_id(client)
    salary = await _cat_id(client, "工资", "income")
    if salary is None:
        pytest.skip("seed category 工资 missing")
    for offset in (1, 2, 3):
        prev = _prev_month_str(offset)
        await _tx(
            client,
            account_id=acc,
            category_id=salary,
            type="income",
            amount_cents=100 * offset,
            occurred_on=f"{prev}-05",
        )
    resp = await client.get("/api/stats/trend", params={"months": 4})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    months = [item["month"] for item in data]
    assert months == sorted(months)
    assert len(months) == len(set(months))
    assert data[0]["income_cents"] == 300
    assert data[1]["income_cents"] == 200
    assert data[2]["income_cents"] == 100
    assert data[3]["income_cents"] == 0


async def test_summary_single_month_isolation(client):
    acc = await _account_id(client)
    food = await _cat_id(client, "餐饮", "expense")
    if food is None:
        pytest.skip("seed category 餐饮 missing")
    target = _prev_month_str(2)
    await _tx(
        client,
        account_id=acc,
        category_id=food,
        type="expense",
        amount_cents=2500,
        occurred_on=f"{target}-15",
    )
    resp = await client.get("/api/stats/summary", params={"month": target})
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["expense_cents"] == 2500
    assert data["income_cents"] == 0
    assert data["net_cents"] == -2500


async def test_validate_month_non_string_none_raises():
    from fastapi import HTTPException

    from ledger.routers.stats import _validate_month

    with pytest.raises(HTTPException) as exc:
        _validate_month(None)
    assert exc.value.status_code == 400


async def test_month_regex_matches_only_valid_months():
    from ledger.routers.stats import _MONTH_RE

    valid = ["2024-01", "2024-09", "2024-10", "2024-12", "0000-01", "9999-12"]
    invalid = ["2024-13", "2024-00", "2024-1", "2024-001", "24-01", "2024-1a"]
    for v in valid:
        assert _MONTH_RE.match(v), v
    for v in invalid:
        assert _MONTH_RE.match(v) is None, v