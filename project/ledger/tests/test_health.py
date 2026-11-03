async def test_health_returns_ok(client):
    response = await client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "version" in data


async def test_unknown_route_returns_404(client):
    response = await client.get("/api/nope")
    assert response.status_code == 404
