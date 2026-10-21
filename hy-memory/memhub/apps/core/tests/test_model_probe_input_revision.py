import asyncio

import httpx
import pytest

from one_memory.model_probe import ModelProber, ModelProbeResult, ProbeCode
from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileConflictError,
    ModelProfileInput,
    ModelProfilePatch,
    ModelProfileStore,
    ProviderKind,
)
from one_memory.secrets import InMemorySecretStore


def environment(tmp_path, *, width=3, provider=ProviderKind.OLLAMA):
    store = ModelProfileStore(tmp_path / "probe.sqlite3")
    secrets = InMemorySecretStore()
    profile = store.create(
        ModelProfileInput(
            name="Synthetic probe",
            provider_kind=provider,
            model="synthetic-model",
            embedding_model="synthetic-embedding",
            embedding_provider_kind=ProviderKind.OLLAMA,
            embedding_base_url="http://127.0.0.1:11434",
            embedding_dimensions=width,
        ),
        secrets,
    )
    return store, secrets, profile


def response(request):
    if request.url.path == "/api/tags":
        return httpx.Response(200, json={"models": [{"name": "synthetic-model"}]})
    if request.url.path == "/api/embed":
        return httpx.Response(200, json={"embeddings": [[0.1, 0.2, 0.3]]})
    assert request.url.path == "/api/chat"
    return httpx.Response(200, json={"message": {"content": '{"memory_probe":true}'}})


@pytest.mark.parametrize("width,completed_revision", [(3, 1), (2, 2), (None, 2)])
def test_input_revision_precedes_measured_width_update(tmp_path, width, completed_revision):
    store, secrets, profile = environment(tmp_path, width=width)
    result = asyncio.run(
        ModelProber(store=store, secrets=secrets, transport=httpx.MockTransport(response)).probe(
            profile.profile_id
        )
    )
    assert result.input_profile_revision == profile.revision == 1
    assert result.profile_revision == completed_revision
    saved = store.require(profile.profile_id, secrets)
    assert saved.revision == completed_revision
    assert saved.embedding_dimensions == 3
    assert result.capabilities == saved.capabilities
    assert result.capabilities.embedding_available
    assert result.model_dump()["input_profile_revision"] == 1


@pytest.mark.parametrize("width", [3, 2])
def test_concurrent_update_still_rejects_width_or_capability_cas(tmp_path, width):
    store, secrets, profile = environment(tmp_path, width=width)
    updated = []

    def racing_response(request):
        if request.url.path == "/api/embed":
            updated.append(
                store.update(
                    profile.profile_id,
                    ModelProfilePatch(expected_revision=1, model="changed-by-other-client"),
                    secrets,
                )
            )
        return response(request)

    with pytest.raises(ModelProfileConflictError):
        asyncio.run(
            ModelProber(
                store=store, secrets=secrets, transport=httpx.MockTransport(racing_response)
            ).probe(profile.profile_id)
        )
    assert len(updated) == 1
    saved = store.require(profile.profile_id, secrets)
    assert saved.revision == 2
    assert saved.model == "changed-by-other-client"
    assert saved.embedding_dimensions == width
    assert saved.capabilities == ModelCapabilities()


@pytest.mark.parametrize(
    "provider,code",
    [
        (ProviderKind.OPENAI_COMPATIBLE, ProbeCode.MISSING_API_KEY),
        (ProviderKind.ANTHROPIC, ProbeCode.STRUCTURED_OUTPUT_UNSUPPORTED),
        (ProviderKind.HY_DEFAULT, ProbeCode.HY_DEFAULT_UNAVAILABLE),
    ],
)
def test_early_returns_record_the_actual_starting_revision(tmp_path, provider, code):
    store, secrets, profile = environment(tmp_path, provider=provider)
    # Another client changed the profile BEFORE this probe began. It must not
    # report the revision remembered by the initiating UI as its input identity.
    store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, name="renamed"), secrets
    )

    def no_network(_request):
        pytest.fail("early return must not send an HTTP request")

    result = asyncio.run(
        ModelProber(store=store, secrets=secrets, transport=httpx.MockTransport(no_network)).probe(
            profile.profile_id
        )
    )
    assert result.input_profile_revision == result.profile_revision == 2
    assert result.stages[0].code == code


def test_endpoint_failure_also_reports_input_revision(tmp_path):
    store, secrets, profile = environment(tmp_path)
    result = asyncio.run(
        ModelProber(
            store=store,
            secrets=secrets,
            transport=httpx.MockTransport(lambda _: httpx.Response(401)),
        ).probe(profile.profile_id)
    )
    assert result.input_profile_revision == result.profile_revision == 1
    assert result.stages[0].code == ProbeCode.UNAUTHORIZED
    assert not result.capabilities.endpoint_reachable


def test_probe_starting_after_an_update_reports_new_input_not_previous_ui_version(tmp_path):
    store, secrets, profile = environment(tmp_path, width=2)
    store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, name="renamed"), secrets
    )
    result = asyncio.run(
        ModelProber(store=store, secrets=secrets, transport=httpx.MockTransport(response)).probe(
            profile.profile_id
        )
    )
    assert result.input_profile_revision == 2
    assert result.profile_revision == 3


def test_old_result_payload_remains_compatible_with_default_none():
    result = ModelProbeResult(
        profile_id="legacy", profile_revision=1, stages=(), capabilities=ModelCapabilities()
    )
    assert result.input_profile_revision is None
