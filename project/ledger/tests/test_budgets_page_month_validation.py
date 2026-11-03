import pytest


@pytest.mark.asyncio
async def test_bogus_month_returns_400(client):
    resp = await client.get("/budgets", params={"month": "bogus"})
    assert resp.status_code == 400
    assert resp.json()["detail"] == "month 参数非法"


@pytest.mark.asyncio
async def test_month_2026_13_returns_400(client):
    resp = await client.get("/budgets", params={"month": "2026-13"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_month_2026_00_returns_400(client):
    resp = await client.get("/budgets", params={"month": "2026-00"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_month_2026_1_returns_400(client):
    resp = await client.get("/budgets", params={"month": "2026-1"})
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_valid_month_returns_200_html(client):
    resp = await client.get("/budgets", params={"month": "2026-10"})
    assert resp.status_code == 200
    assert "text/html" in resp.headers["content-type"]


@pytest.mark.asyncio
async def test_missing_month_returns_200(client):
    resp = await client.get("/budgets")
    assert resp.status_code == 200
