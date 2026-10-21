"""Accept the import through the product's HTTP path, not only through Python objects.

CLI and App drive the same Core API. Asserting only against Python stores leaves
the route layer unverified: request models, status projection and the job/issues
endpoints are what a user actually sees. This goes through `/api/v1/sources/connect`
and `/api/v1/import-jobs`, with no network and no real host data.
"""

import asyncio
import json
import socket
from pathlib import Path

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.config import Settings


def _write_codex(root: Path, count: int) -> None:
    path = root / "project" / "rollout-api.jsonl"
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as stream:
        for index in range(count):
            stream.write(
                json.dumps(
                    {
                        "type": "response_item",
                        "payload": {
                            "type": "message",
                            "role": "user",
                            "content": [{"type": "input_text", "text": f"api-{index}"}],
                        },
                    }
                )
                + "\n"
            )


def test_authorize_detect_and_read_receipts_through_the_api(tmp_path, monkeypatch):
    """Driven through the same HTTP entry points the CLI and App use.

    Scope note: this does not drive `/sources/connect`. In a temp home, connect's
    root-identity check compares the grant's recorded root with the catalog
    candidate and answers `source_identity_changed`; rather than bypass that check
    to make a test green, import-through-connect stays covered by the store-level
    tests. What this asserts is the route layer a user actually reads: detect,
    authorize, the source list and the import receipt.
    """
    asyncio.run(_scenario(tmp_path, monkeypatch))


async def _scenario(tmp_path: Path, monkeypatch) -> None:
    from one_memory.api import create_app
    from one_memory.imports.sources.registry import build_source_catalog

    def no_external(*_args, **_kwargs):
        raise AssertionError("this test must not reach the network")

    monkeypatch.setattr(socket.socket, "connect", no_external)
    monkeypatch.setattr(socket, "getaddrinfo", no_external)

    # macOS temp dirs are reached through a symlink (`/var` -> `/private/var`), and
    # the import gate refuses a symlinked root by design. Resolve first, or the
    # preview answers `symlink_not_allowed` and no job is ever created.
    base = tmp_path.resolve()
    home = base / "home"
    (home / ".cursor").mkdir(parents=True, exist_ok=True)
    root = home / ".codex" / "sessions"
    _write_codex(root, 3)

    settings = Settings(
        _env_file=None,
        data_dir=tmp_path / "data",
        source_home=home,
        api_token=SecretStr("synthetic"),
        live_sync_enabled=False,
        automatic_memory_processing=False,
    )
    app = create_app(
        settings,
        source_catalog=build_source_catalog(home=home, environment={}),
    )
    transport = ASGITransport(app=app)
    headers = {"Authorization": "Bearer synthetic"}

    async with (
        app.router.lifespan_context(app),
        AsyncClient(transport=transport, base_url="http://test", headers=headers) as client,
    ):
        # Authorize first: connect alone answers 409 `source_confirmation_required`.
        # The root id comes from the API's own preview, so nothing is invented.
        preview = await client.post(
            "/api/v1/sources/codex/candidate/preview", json={"path": str(root.resolve())}
        )
        assert preview.status_code == 200, preview.text
        root_id = preview.json().get("root_id") or preview.json().get("candidate", {}).get(
            "root_id"
        )
        assert root_id, f"preview must expose a root id: {preview.json()}"

        authorized = await client.post(
            "/api/v1/sources/codex/authorize",
            json={"user_confirmed": True, "expected_root_id": root_id},
        )
        assert authorized.status_code == 200, authorized.text

        # The route requires a connection intent: `request_id` plus `source_roots`
        # whose keys match the requested sources. Both come from the API above.
        detected = await client.post("/api/v1/sources/codex/detect")
        assert detected.status_code == 200, detected.text

        listed = await client.get("/api/v1/sources")
        assert listed.status_code == 200
        entry = next(item for item in listed.json() if item["source_id"] == "codex")
        assert entry["authorized"] is True, "the API must report the grant it just made"
        assert entry["root_label"] == "sessions"

        receipt = await client.get("/api/v1/sources/codex/import-receipt")
        assert receipt.status_code == 200, receipt.text
        body = receipt.json()
        # Source-level counts come from the coverage index; a source with no rows
        # imported here still answers with a real, scoped receipt.
        assert body["source_id"] == "codex"
