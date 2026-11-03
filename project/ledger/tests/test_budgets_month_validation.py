from __future__ import annotations

import pytest


@pytest.mark.asyncio
async def test_list_budgets_month_bogus_returns_400(client):
    resp = await client.get("/api/budgets", params={"month": "bogus"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "month 参数非法"


@pytest.mark.asyncio
async def test_list_budgets_month_13_returns_400(client):
    resp = await client.get("/api/budgets", params={"month": "2026-13"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "month 参数非法"


@pytest.mark.asyncio
async def test_list_budgets_month_00_returns_400(client):
    resp = await client.get("/api/budgets", params={"month": "2026-00"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "month 参数非法"


@pytest.mark.asyncio
async def test_list_budgets_month_short_returns_400(client):
    resp = await client.get("/api/budgets", params={"month": "2026-1"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "month 参数非法"


@pytest.mark.asyncio
async def test_list_budgets_month_empty_returns_400(client):
    resp = await client.get("/api/budgets", params={"month": ""})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "month 参数非法"


@pytest.mark.asyncio
async def test_list_budgets_month_valid_returns_200(client):
    resp = await client.get("/api/budgets", params={"month": "2026-10"})
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)
