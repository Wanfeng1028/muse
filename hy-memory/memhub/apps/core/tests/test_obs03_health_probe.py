"""OBS-03: `/health` answered with the web app instead of a health payload.

The single-page app owns a `/{path:path}` catch-all that answers every unknown
path with index.html. A probe that asks `/health` therefore got a 200 HTML page
and read it as a healthy Core, which is exactly how a stopped Core can look
alive. `/health` must answer the real payload.
"""

from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings


def test_bare_health_answers_the_health_payload(tmp_path) -> None:
    app = create_app(
        settings=Settings(
            data_dir=tmp_path / "data",
            source_home=tmp_path,
            api_token=SecretStr("local-token"),
        )
    )

    async def run() -> None:
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer local-token"},
            ) as client,
        ):
            reply = await client.get("/health")
            assert reply.status_code == 200
            body = reply.json()
            assert body["service"] == "one-memory-core"
            assert "version" in body

    asyncio.run(run())
