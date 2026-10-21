"""The `POST /api/v1/backup` endpoint the CLI's `backup create` calls.

Two properties matter and both are asserted:

1. It makes a real, readable copy — not just a 200 with a path.
2. It refuses a target outside the data dir. The CLI can name any path, so an
   unrestricted write here would turn a read-only client into a file-write
   primitive.
"""

from __future__ import annotations

import sqlite3

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings


def _client(tmp_path):
    """App plus an authorized client, matching the other API tests.

    The lifespan context is what populates `app.state.evidence_store`; without
    it the route raises AttributeError rather than exercising anything.
    """
    app = create_app(
        Settings(
            _env_file=None,
            data_dir=tmp_path,
            source_home=tmp_path,
            api_token=SecretStr("test-token"),
        )
    )
    return app, AsyncClient(
        transport=ASGITransport(app=app),
        base_url="http://test",
        headers={
            "Authorization": "Bearer test-token",
            "Origin": "http://127.0.0.1:5173",
        },
    )


@pytest.mark.anyio
async def test_backup_writes_a_readable_copy(tmp_path) -> None:
    app, client = _client(tmp_path)
    async with app.router.lifespan_context(app), client:
        response = await client.post(
            "/api/v1/backup",
            json={"target": "backups/one.sqlite3"},
        )

    assert response.status_code == 200, response.text
    body = response.json()
    target = tmp_path / "backups" / "one.sqlite3"
    assert body["bytes"] == target.stat().st_size
    assert body["bytes"] > 0

    # A backup that cannot be opened is worse than none: it looks like safety
    # and is not.
    connection = sqlite3.connect(target)
    try:
        tables = connection.execute(
            "SELECT COUNT(*) FROM sqlite_master WHERE type='table'"
        ).fetchone()[0]
    finally:
        connection.close()
    assert tables > 0, "backup is not a readable database"


@pytest.mark.anyio
async def test_backup_refuses_a_target_outside_the_data_dir(tmp_path) -> None:
    app, client = _client(tmp_path)
    async with app.router.lifespan_context(app), client:
        response = await client.post(
            "/api/v1/backup",
            json={"target": "/tmp/definitely-outside.sqlite3"},
        )

    assert response.status_code == 422
    assert response.json()["detail"] == "backup_target_outside_data_dir"
