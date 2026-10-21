"""3925a kernel item 3: the error code reaches the HTTP boundary.

The frontend needs three different sentences. Core currently sends
`secure_storage_unavailable` for all of them, so a user whose Keychain is
waiting for one click is told the store is broken and there is nothing to do.
"""

from __future__ import annotations

import asyncio

from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.secrets import (
    InMemorySecretStore,
    SecretStoreErrorCode,
    SecretStoreUnavailableError,
)


class RefusingWritesSecretStore(InMemorySecretStore):
    """Accepts nothing, with a chosen code for why.

    The endpoints that merely project a credential (`list`, `delete`) degrade
    on purpose: a profile the store cannot read is reported as having no key
    rather than failing the whole page. So the code has to be observed where
    the store is genuinely required, which is writing one.
    """

    code = SecretStoreErrorCode.STORE_UNAVAILABLE

    def put(self, secret_ref: str, value: str) -> None:
        raise SecretStoreUnavailableError("synthetic refusal", code=self.code)

    def resolve(self, secret_ref: str) -> str | None:
        raise SecretStoreUnavailableError("synthetic refusal", code=self.code)

    def has(self, secret_ref: str) -> bool:
        return self.resolve(secret_ref) is not None


def _scenario(tmp_path, code) -> tuple[int, object]:
    async def run() -> tuple[int, object]:
        app = create_app(
            Settings(
                data_dir=tmp_path / "data",
                source_home=tmp_path / "home",
                api_token=SecretStr("test-token"),
                automatic_memory_processing=False,
                live_sync_enabled=False,
                live_sync_watch_enabled=False,
            )
        )
        async with (
            app.router.lifespan_context(app),
            AsyncClient(
                transport=ASGITransport(app=app),
                base_url="http://test",
                headers={"Authorization": "Bearer test-token"},
            ) as client,
        ):
            # Installed after the lifespan: that is when the real store lands,
            # and the failure under test is what happens on the first write.
            store = RefusingWritesSecretStore()
            store.code = code
            app.state.secret_store = store
            response = await client.post(
                "/api/v1/model-profiles",
                json={
                    "name": "Synthetic profile",
                    "provider_kind": "openai_compatible",
                    "model": "synthetic-model",
                    "api_key": "synthetic-credential",
                },
            )
            return response.status_code, response.json()

    return asyncio.run(run())


def test_authorization_required_reaches_the_client(tmp_path) -> None:
    status, body = _scenario(tmp_path, SecretStoreErrorCode.AUTHORIZATION_REQUIRED)

    assert status == 503
    assert body == {"detail": "secure_storage_authorization_required"}


def test_a_read_timeout_reaches_the_client(tmp_path) -> None:
    status, body = _scenario(tmp_path, SecretStoreErrorCode.READ_TIMEOUT)

    assert status == 503
    assert body == {"detail": "secure_storage_read_timeout"}


def test_an_unavailable_store_reaches_the_client(tmp_path) -> None:
    status, body = _scenario(tmp_path, SecretStoreErrorCode.STORE_UNAVAILABLE)

    assert status == 503
    assert body == {"detail": "secure_storage_unavailable"}
