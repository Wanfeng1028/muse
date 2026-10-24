import json
import sys
from pathlib import Path
from time import perf_counter

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
from load_test import COLUMN_MAPPING, MERCHANTS, generate_month_csv


async def _ensure_account(client) -> int:
    resp = await client.post(
        "/api/accounts",
        json={
            "name": "LoadTestAccount",
            "type": "savings",
            "currency": "CNY",
            "opening_balance_cents": 0,
        },
    )
    if resp.status_code in (200, 201):
        return resp.json()["id"]
    resp = await client.get("/api/accounts")
    return resp.json()[0]["id"]


async def _category_map(client) -> dict:
    resp = await client.get("/api/categories")
    return {c["name"]: c["id"] for c in resp.json()}


async def _upload(client, aid: int, year: int, month: int) -> tuple[dict, list]:
    csv_text, expected = generate_month_csv(year, month, seed=20261024)
    resp = await client.post(
        "/api/statements/upload",
        files={"file": ("m.csv", csv_text.encode("utf-8"), "text/csv")},
        data={
            "account_id": str(aid),
            "mapping": json.dumps(COLUMN_MAPPING),
        },
    )
    assert resp.status_code == 200
    return resp.json(), expected


async def test_load_two_months(client):
    aid = await _ensure_account(client)
    up0, exp0 = await _upload(client, aid, 2024, 10)
    up1, exp1 = await _upload(client, aid, 2024, 11)

    assert up0["parsed"] + up1["parsed"] == len(exp0) + len(exp1)

    for up in (up0, up1):
        bid = up["batch"]["id"]
        resp = await client.post(f"/api/statements/{bid}/confirm")
        assert resp.status_code == 200
        confirmed = resp.json()
        assert confirmed["total_count"] == up["parsed"]
        assert confirmed["status"] != "preview"


async def test_load_dedup(client):
    aid = await _ensure_account(client)
    up_first, _ = await _upload(client, aid, 2024, 10)
    bid = up_first["batch"]["id"]
    resp = await client.post(f"/api/statements/{bid}/confirm")
    assert resp.status_code == 200

    up_dup, _ = await _upload(client, aid, 2024, 10)
    assert up_dup["duplicates_skipped"] == up_first["parsed"]
    assert up_dup["batch"]["total_count"] == 0


async def test_load_auto_match(client):
    aid = await _ensure_account(client)
    cat_map = await _category_map(client)

    eligible = [m for m in MERCHANTS if m.get("monthly", 0) >= 4 and m["category"] in cat_map]
    for merch in eligible:
        rule_resp = await client.post(
            "/api/match-rules",
            json={
                "keyword": merch["name"],
                "category_id": cat_map[merch["category"]],
                "direction": merch["direction"],
                "priority": 10,
                "pattern_type": "keyword",
                "is_enabled": 1,
            },
        )
        assert rule_resp.status_code in (200, 201, 409)

    up, _ = await _upload(client, aid, 2024, 10)
    bid = up["batch"]["id"]

    resp = await client.post(f"/api/statements/{bid}/confirm")
    assert resp.status_code == 200
    confirmed = resp.json()
    auto_count = confirmed["auto_count"]
    total_count = confirmed["total_count"]
    assert total_count > 0
    assert auto_count / total_count >= 0.5

    top_merch = max(eligible, key=lambda m: m["monthly"])
    rule_cat_id = cat_map[top_merch["category"]]

    items_resp = await client.get(f"/api/statements/{bid}/items?limit=500&offset=0")
    items_data = items_resp.json()
    items = items_data["items"] if isinstance(items_data, dict) else items_data

    for item in items:
        if item.get("suggested_rule_id") is not None:
            if top_merch["name"] in (item.get("counterparty") or ""):
                assert item["suggested_category_id"] == rule_cat_id


async def test_load_confirm_timing(client):
    aid = await _ensure_account(client)
    up, _ = await _upload(client, aid, 2024, 10)
    bid = up["batch"]["id"]

    t0 = perf_counter()
    resp = await client.post(f"/api/statements/{bid}/confirm")
    elapsed = perf_counter() - t0
    assert resp.status_code == 200
    assert elapsed < 60
    print(f"confirm elapsed: {elapsed:.2f}s")
