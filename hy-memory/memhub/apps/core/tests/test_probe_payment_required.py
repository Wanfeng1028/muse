import asyncio

import httpx
from pydantic import SecretStr

from one_memory.model_probe import ModelProber, ProbeCode
from one_memory.model_profiles import ModelProfileInput, ModelProfileStore, ProviderKind
from one_memory.secrets import InMemorySecretStore

API_KEY = "probe-secret-value"


def _probe(handler, tmp_path):
    store = ModelProfileStore(tmp_path / "one-memory.sqlite3")
    secrets = InMemorySecretStore()
    profile = store.create(
        ModelProfileInput(
            name="Provider",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://models.example.com/v1",
            model="memory-model",
            api_key=SecretStr(API_KEY),
        ),
        secrets,
    )
    return asyncio.run(
        ModelProber(store=store, secrets=secrets, transport=httpx.MockTransport(handler)).probe(
            profile.profile_id
        )
    )


def _generation_only(handler):
    """Answer the model list, then let the caller answer the generation call."""

    def respond(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/models"):
            return httpx.Response(200, json={"data": [{"id": "memory-model"}]})
        return handler(request)

    return respond


def test_http_402_without_a_useful_body_is_still_understood_as_unpaid(tmp_path) -> None:
    """A gateway that returns 402 and says nothing useful still means unpaid.

    The body classifier only recognised a balance error when the body spelled
    one out. A bare 402 fell through to INVALID_RESPONSE, which reads as a
    broken endpoint and sends someone to change the address instead of to pay.
    """

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(402, json={"error": {"message": ""}})

    result = _probe(_generation_only(handler), tmp_path)

    assert result.stages[1].code is ProbeCode.INSUFFICIENT_BALANCE


def test_a_wrong_address_is_still_a_missing_model_not_an_unpaid_one(tmp_path) -> None:
    """404 stays its own thing: the fix is the address, and it is free."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": {"message": "no such route"}})

    result = _probe(_generation_only(handler), tmp_path)

    assert result.stages[1].code is ProbeCode.MODEL_NOT_FOUND
