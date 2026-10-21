import asyncio
import json
import sqlite3

import httpx
import pytest

from one_memory.matters.model import MatterModel
from one_memory.model_profiles import ModelProfileInput, ModelProfileStore, ProviderKind
from one_memory.secrets import InMemorySecretStore


def model_for(tmp_path, respond):
    profiles = ModelProfileStore(tmp_path / "model.sqlite3")
    secrets = InMemorySecretStore()
    profile = profiles.create(
        ModelProfileInput(name="test", provider_kind=ProviderKind.OLLAMA, model="test"), secrets
    )
    return MatterModel(profiles, secrets, transport=httpx.MockTransport(respond)), profile


@pytest.mark.parametrize("failure", ["timeout", "connect", "503"])
def test_transient_failure_retries_identical_request_once(tmp_path, failure):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        if len(requests) == 1:
            if failure == "timeout":
                raise httpx.ReadTimeout("private provider details", request=request)
            if failure == "connect":
                raise httpx.ConnectError("private provider details", request=request)
            return httpx.Response(503)
        return httpx.Response(200, json={"message": {"content": '{"ok":true}'}})

    model, profile = model_for(tmp_path, respond)
    assert asyncio.run(model.complete("native", {}, profile_id=profile.profile_id)) == {"ok": True}
    assert len(requests) == 2 and requests[0] == requests[1]


def test_repeated_timeout_is_bounded_and_not_cached(tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        raise httpx.ReadTimeout("private provider details", request=request)

    model, profile = model_for(tmp_path, respond)
    with pytest.raises(ValueError, match="^matter_model_timeout$"):
        asyncio.run(model.complete("native", {}, profile_id=profile.profile_id))
    assert len(calls) == 2
    with sqlite3.connect(model.profiles.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM matter_model_cache").fetchone()[0] == 0


def test_revocation_stops_retry_before_another_request(tmp_path):
    requests = []

    def respond(request):
        requests.append(request)
        raise httpx.ConnectError("lost connection", request=request)

    model, profile = model_for(tmp_path, respond)

    def guard():
        if requests:
            raise ValueError("matter_sources_changed_during_generation")

    model.evidence_guard = guard
    with pytest.raises(ValueError, match="sources_changed"):
        asyncio.run(model.complete("native", {}, profile_id=profile.profile_id))
    assert len(requests) == 1


def test_malformed_json_is_explicit_and_never_cached(tmp_path):
    model, profile = model_for(
        tmp_path, lambda _: httpx.Response(200, json={"message": {"content": "not json"}})
    )
    with pytest.raises(ValueError, match="^matter_model_invalid_json$"):
        asyncio.run(model.complete("native", {}, profile_id=profile.profile_id))


def test_invalid_json_gets_one_format_retry_with_the_same_source_input(tmp_path):
    requests = []

    def respond(request):
        requests.append(json.loads(request.content))
        return httpx.Response(
            200, json={"message": {"content": "not json" if len(requests) == 1 else '{"ok":true}'}}
        )

    model, profile = model_for(tmp_path, respond)
    assert asyncio.run(
        model.complete("native", {"source": "unchanged"}, profile_id=profile.profile_id)
    ) == {"ok": True}
    assert len(requests) == 2
    assert requests[1]["messages"][:2] == requests[0]["messages"]
    assert "JSON" in requests[1]["messages"][-1]["content"]


def test_json_retry_is_bounded_and_never_caches_invalid_content(tmp_path):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"message": {"content": "not json"}})

    model, profile = model_for(tmp_path, respond)
    with pytest.raises(ValueError, match="^matter_model_invalid_json$"):
        asyncio.run(model.complete("native", {}, profile_id=profile.profile_id))
    assert len(requests) == 2
    with sqlite3.connect(model.profiles.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM matter_model_cache").fetchone()[0] == 0


def test_revocation_during_request_prevents_caching_or_returning_the_result(tmp_path):
    requests = []

    def respond(request):
        requests.append(request)
        return httpx.Response(200, json={"message": {"content": '{"ok":true}'}})

    model, profile = model_for(tmp_path, respond)

    def guard():
        if requests:
            raise ValueError("matter_sources_changed_during_generation")

    model.evidence_guard = guard
    with pytest.raises(ValueError, match="sources_changed"):
        asyncio.run(model.complete("native", {}, profile_id=profile.profile_id))
    with sqlite3.connect(model.profiles.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM matter_model_cache").fetchone()[0] == 0


def test_authentication_error_is_not_retried(tmp_path):
    calls = []

    def respond(request):
        calls.append(request)
        return httpx.Response(401, json={"error": {"message": "private details"}})

    model, profile = model_for(tmp_path, respond)
    with pytest.raises(ValueError, match="^matter_model_http_401$"):
        asyncio.run(model.complete("native", {}, profile_id=profile.profile_id))
    assert len(calls) == 1
