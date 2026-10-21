import asyncio

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.secrets import InMemorySecretStore


def _settings(tmp_path):
    return Settings(
        _env_file=None,
        data_dir=tmp_path,
        source_home=tmp_path / "source",
        imports_enabled=False,
        automatic_memory_processing=False,
        live_sync_enabled=False,
        api_token=SecretStr("test-token"),
    )


def test_ui_session_exchange_sets_httponly_strict_cookie(tmp_path, monkeypatch) -> None:
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>console</html>\n")
    monkeypatch.setenv("ONE_MEMORY_WEB_DIR", str(web))
    monkeypatch.setattr("one_memory.model_presets._preset_data", lambda: None)
    app = create_app(_settings(tmp_path), secret_store=InMemorySecretStore())

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                created = await client.post(
                    "/api/v1/ui/session",
                    headers={"Authorization": "Bearer test-token"},
                )
                assert created.status_code == 200
                document = created.json()
                code = document["exchange_code"]

                login = await client.get(
                    "/ui/login",
                    params={"code": code},
                    follow_redirects=False,
                )
                assert login.status_code == 303
                cookie = login.headers["set-cookie"]
                assert "HttpOnly" in cookie
                assert "SameSite=strict" in cookie
                assert "test-token" not in cookie

                # The browser cookie authenticates a protected API call.
                identity = await client.get("/api/v1/runtime/identity")
                assert identity.status_code == 200

                # A code is single-use.
                replay = await client.get(
                    "/ui/login",
                    params={"code": code},
                    follow_redirects=False,
                )
                assert replay.status_code == 401
                assert replay.json()["detail"] == "ui_session_code_invalid"

                # Logout invalidates the browser session and clears the cookie.
                logged_out = await client.post("/api/v1/ui/session/logout")
                assert logged_out.status_code == 200
                assert "one_memory_session=" in logged_out.headers["set-cookie"]
                after_logout = await client.get("/api/v1/runtime/identity")
                assert after_logout.status_code == 401

    asyncio.run(scenario())


def test_ui_session_requires_bearer_for_exchange(tmp_path, monkeypatch) -> None:
    web = tmp_path / "web"
    (web / "assets").mkdir(parents=True)
    (web / "index.html").write_text("<html>console</html>\n")
    monkeypatch.setenv("ONE_MEMORY_WEB_DIR", str(web))
    monkeypatch.setattr("one_memory.model_presets._preset_data", lambda: None)
    app = create_app(_settings(tmp_path), secret_store=InMemorySecretStore())

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post("/api/v1/ui/session")
                assert response.status_code == 401

    asyncio.run(scenario())


def test_ui_session_reports_missing_web_assets(tmp_path, monkeypatch) -> None:
    monkeypatch.delenv("ONE_MEMORY_WEB_DIR", raising=False)
    monkeypatch.setattr("one_memory.model_presets._preset_data", lambda: None)
    app = create_app(_settings(tmp_path), secret_store=InMemorySecretStore())

    async def scenario() -> None:
        async with app.router.lifespan_context(app):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as client:
                response = await client.post(
                    "/api/v1/ui/session",
                    headers={"Authorization": "Bearer test-token"},
                )
                assert response.status_code == 503
                assert response.json()["detail"] == "ui_web_assets_unavailable"

    asyncio.run(scenario())
