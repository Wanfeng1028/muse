import pytest

pytestmark = pytest.mark.asyncio


async def test_yearly_year_abcd_400(client):
    resp = await client.get("/api/budgets/yearly", params={"year": "abcd"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "year 参数非法"


async def test_yearly_year_26_400(client):
    resp = await client.get("/api/budgets/yearly", params={"year": "26"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "year 参数非法"


async def test_yearly_year_20261_400(client):
    resp = await client.get("/api/budgets/yearly", params={"year": "20261"})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "year 参数非法"


async def test_yearly_year_trailing_space_400(client):
    resp = await client.get("/api/budgets/yearly", params={"year": "2026 "})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "year 参数非法"


async def test_yearly_year_empty_400(client):
    resp = await client.get("/api/budgets/yearly", params={"year": ""})
    assert resp.status_code == 400, resp.text
    assert resp.json()["detail"] == "year 参数非法"


async def test_yearly_year_valid_200(client):
    resp = await client.get("/api/budgets/yearly", params={"year": "2026"})
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["year"] == "2026"
    assert len(body["months"]) == 12
