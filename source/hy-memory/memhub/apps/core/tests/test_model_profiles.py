import sqlite3

import pytest
from pydantic import SecretStr, ValidationError

from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileConflictError,
    ModelProfileInput,
    ModelProfilePatch,
    ModelProfileStore,
    ModelProfileUnavailableError,
    ProviderKind,
    validate_model_base_url,
)
from one_memory.secrets import InMemorySecretStore

API_KEY = "key-that-must-never-enter-sqlite"


def test_profile_uses_one_model_and_keeps_key_out_of_database(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    secrets = InMemorySecretStore()
    store = ModelProfileStore(database)

    profile = store.create(
        ModelProfileInput(
            name="Local-compatible",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="http://127.0.0.1:8080/v1",
            model="memory-model",
            api_key=SecretStr(API_KEY),
        ),
        secrets,
    )

    assert profile.has_api_key is True
    assert "api_key" not in profile.model_dump()
    assert API_KEY.encode() not in database.read_bytes()
    assert secrets.resolve(store.secret_ref(profile.profile_id) or "") == API_KEY


def test_api_key_updates_reuse_one_stable_secret_reference(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    secrets = InMemorySecretStore()
    store = ModelProfileStore(database)
    profile = store.create(
        ModelProfileInput(
            name="Remote",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://models.example.com/v1",
            model="memory-model",
            api_key=SecretStr("first-key"),
        ),
        secrets,
    )

    reference = store.secret_ref(profile.profile_id)
    updated = store.update(
        profile.profile_id,
        ModelProfilePatch(expected_revision=1, api_key=SecretStr("second-key")),
        secrets,
    )

    assert reference == f"model-profile:{profile.profile_id}"
    assert store.secret_ref(profile.profile_id) == reference
    assert secrets.resolve(reference) == "second-key"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT DISTINCT secret_ref FROM model_profile_versions WHERE profile_id=?",
            (profile.profile_id,),
        ).fetchall() == [(reference,)]
    assert updated.revision == 2


def test_startup_cleanup_removes_only_secrets_not_referenced_by_current_profiles(tmp_path) -> None:
    database = tmp_path / "one-memory.sqlite3"
    secrets = InMemorySecretStore()
    store = ModelProfileStore(database)
    profile = store.create(
        ModelProfileInput(
            name="Remote",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://models.example.com/v1",
            model="memory-model",
            api_key=SecretStr("current-key"),
        ),
        secrets,
    )
    current_ref = store.secret_ref(profile.profile_id)
    stale_ref = f"model-profile:{profile.profile_id}:revision:0"
    secrets.put(stale_ref, "stale-key")
    with sqlite3.connect(database) as connection, connection:
        connection.execute(
            "UPDATE model_profile_versions SET secret_ref=? WHERE profile_id=? AND revision=1",
            (stale_ref, profile.profile_id),
        )

    assert store.cleanup_unreferenced_secrets(secrets) == 1
    assert secrets.resolve(stale_ref) is None
    assert secrets.resolve(current_ref) == "current-key"
    with sqlite3.connect(database) as connection:
        assert connection.execute(
            "SELECT secret_ref FROM model_profile_versions WHERE profile_id=? AND revision=1",
            (profile.profile_id,),
        ).fetchone() == (None,)


def test_remote_generation_can_use_local_ollama_embedding(tmp_path) -> None:
    store = ModelProfileStore(tmp_path / "one-memory.sqlite3")
    secrets = InMemorySecretStore()

    profile = store.create(
        ModelProfileInput(
            name="Remote generation",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://models.example.com/v1",
            model="memory-model",
            embedding_model="nomic-embed-text",
            embedding_provider_kind=ProviderKind.OLLAMA,
            embedding_base_url="http://127.0.0.1:11434",
            api_key=SecretStr(API_KEY),
        ),
        secrets,
    )
    snapshot = store.snapshot(profile.profile_id, profile.revision)

    assert profile.embedding_provider_kind is ProviderKind.OLLAMA
    assert profile.embedding_base_url == "http://127.0.0.1:11434"
    assert snapshot.embedding_provider_kind is ProviderKind.OLLAMA
    assert snapshot.embedding_base_url == "http://127.0.0.1:11434"


def test_remote_embedding_cannot_receive_generation_key_on_another_origin() -> None:
    with pytest.raises(ValidationError, match="share the generation endpoint origin"):
        ModelProfileInput(
            name="Unsafe split credential",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://generation.example.com/v1",
            model="memory-model",
            embedding_model="embedding-model",
            embedding_provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            embedding_base_url="https://embedding.example.com/v1",
            api_key=SecretStr(API_KEY),
        )


def test_remote_embedding_may_share_generation_origin_and_key() -> None:
    profile = ModelProfileInput(
        name="Same provider credential",
        provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        base_url="https://models.example.com/v1",
        model="memory-model",
        embedding_model="embedding-model",
        embedding_provider_kind=ProviderKind.OPENAI_COMPATIBLE,
        embedding_base_url="https://models.example.com/embedding/v1",
        api_key=SecretStr(API_KEY),
    )

    assert profile.embedding_base_url == "https://models.example.com/embedding/v1"


def test_revision_compare_and_swap_prevents_stale_update(tmp_path) -> None:
    store = ModelProfileStore(tmp_path / "one-memory.sqlite3")
    secrets = InMemorySecretStore()
    profile = store.create(
        ModelProfileInput(
            name="Ollama",
            provider_kind=ProviderKind.OLLAMA,
            model="qwen",
        ),
        secrets,
    )

    updated = store.update(
        profile.profile_id,
        ModelProfilePatch(expected_revision=1, model="qwen-new"),
        secrets,
    )

    assert updated.revision == 2
    assert store.snapshot(profile.profile_id, 1).model == "qwen"
    assert store.snapshot(profile.profile_id, 2).model == "qwen-new"
    with pytest.raises(ModelProfileConflictError):
        store.update(
            profile.profile_id,
            ModelProfilePatch(expected_revision=1, model="stale"),
            secrets,
        )


def test_active_profile_can_be_deleted_without_changing_other_profiles(tmp_path) -> None:
    store = ModelProfileStore(tmp_path / "one-memory.sqlite3")
    secrets = InMemorySecretStore()
    other = store.create(
        ModelProfileInput(
            name="Other",
            provider_kind=ProviderKind.OLLAMA,
            model="other",
            embedding_model="nomic-embed-text",
        ),
        secrets,
    )
    profile = store.create(
        ModelProfileInput(
            name="OpenAI compatible",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://models.example.com/v1",
            model="qwen",
            embedding_model="nomic-embed-text",
            api_key=SecretStr(API_KEY),
        ),
        secrets,
    )
    store.record_capabilities(
        profile.profile_id,
        expected_revision=profile.revision,
        capabilities=ModelCapabilities(
            endpoint_reachable=True,
            model_available=True,
            structured_output=True,
            embedding_available=True,
        ),
        secrets=secrets,
    )
    store.activate(profile.profile_id, secrets)
    secret_ref = store.secret_ref(profile.profile_id)

    store.delete(profile.profile_id, secrets)
    assert [item.profile_id for item in store.list(secrets)] == [other.profile_id]
    assert secret_ref is not None
    assert secrets.resolve(secret_ref) is None


@pytest.mark.parametrize(
    "url",
    [
        "file:///private/model",
        "http://example.com/v1",
        "https://user:password@example.com/v1",
        "javascript:alert(1)",
    ],
)
def test_unsafe_model_urls_are_rejected(url: str) -> None:
    with pytest.raises((ValueError, ValidationError)):
        validate_model_base_url(url)


def test_remote_https_and_loopback_http_are_allowed() -> None:
    validate_model_base_url("https://api.example.com/v1")
    validate_model_base_url("http://localhost:11434")
    validate_model_base_url("http://[::1]:8080/v1")


@pytest.mark.parametrize(
    "url",
    [
        "http://models.corp.example/v1",
        "http://api.example.com/v1",
        "http://models.internal.example/v1",
        "http://private-gateway.example/v1",
    ],
)
def test_every_remote_plain_http_endpoint_is_rejected(url: str) -> None:
    """The open build has one rule: remote model traffic requires TLS."""
    with pytest.raises((ValueError, ValidationError)):
        validate_model_base_url(url)


def test_clear_key_purges_current_and_historical_secret(
    tmp_path,
) -> None:
    database = tmp_path / "one-memory.sqlite3"
    store = ModelProfileStore(database)
    secrets = InMemorySecretStore()
    profile = store.create(
        ModelProfileInput(
            name="Provider",
            provider_kind=ProviderKind.ANTHROPIC,
            model="claude",
            api_key=SecretStr(API_KEY),
        ),
        secrets,
    )

    updated = store.update(
        profile.profile_id,
        ModelProfilePatch(expected_revision=1, clear_api_key=True),
        secrets,
    )

    assert updated.has_api_key is False
    assert store.resolve_snapshot_secret(profile.profile_id, 1, secrets) is None
    assert store.resolve_snapshot_secret(profile.profile_id, 2, secrets) is None
    connection = sqlite3.connect(database)
    assert (
        connection.execute(
            "SELECT secret_ref FROM model_profiles WHERE profile_id = ?",
            (profile.profile_id,),
        ).fetchone()[0]
        is None
    )
    connection.close()


def test_key_rotation_is_versioned_and_stale_probe_cannot_overwrite_profile(
    tmp_path,
) -> None:
    store = ModelProfileStore(tmp_path / "one-memory.sqlite3")
    secrets = InMemorySecretStore()
    profile = store.create(
        ModelProfileInput(
            name="Provider",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model="memory-model",
            api_key=SecretStr("first-key"),
        ),
        secrets,
    )
    updated = store.update(
        profile.profile_id,
        ModelProfilePatch(
            expected_revision=1,
            api_key=SecretStr("second-key"),
        ),
        secrets,
    )

    assert store.resolve_snapshot_secret(profile.profile_id, 1, secrets) == "second-key"
    assert store.resolve_snapshot_secret(profile.profile_id, 2, secrets) == "second-key"
    with pytest.raises(ModelProfileConflictError):
        store.record_capabilities(
            profile.profile_id,
            expected_revision=1,
            capabilities=ModelCapabilities(
                endpoint_reachable=True,
                model_available=True,
                structured_output=True,
            ),
            secrets=secrets,
        )
    assert updated.capabilities == ModelCapabilities()


def _probed(store, secrets, *, structured: bool, generates: bool = True):
    profile = store.create(
        ModelProfileInput(
            name="Compatible provider",
            provider_kind=ProviderKind.OLLAMA,
            model="qwen",
            embedding_model="nomic-embed-text",
        ),
        secrets,
    )
    store.record_capabilities(
        profile.profile_id,
        expected_revision=profile.revision,
        capabilities=ModelCapabilities(
            endpoint_reachable=True,
            model_available=generates,
            structured_output=structured,
            embedding_available=True,
        ),
        secrets=secrets,
    )
    return profile


def test_a_model_that_cannot_be_schema_constrained_can_still_be_turned_on(tmp_path) -> None:
    """约束不了 schema 不该拦住整张卡被启用。

    A compatible endpoint may reject response_format while still generating
    valid prompted JSON. HY does not require that optional constraint.
    """
    store = ModelProfileStore(tmp_path / "one-memory.sqlite3")
    secrets = InMemorySecretStore()
    profile = _probed(store, secrets, structured=False)

    active = store.activate(profile.profile_id, secrets)

    assert active.is_active is True
    # 启用了，但不谎报能力：约束不了就是约束不了。
    assert active.capabilities.structured_output is False


def test_a_model_that_cannot_generate_still_cannot_be_turned_on(tmp_path) -> None:
    """正向对照：真的生成不了时照旧拦住。

    没有这条，上一条可以被「把这段判据整体删掉」骗过。
    """
    store = ModelProfileStore(tmp_path / "one-memory.sqlite3")
    secrets = InMemorySecretStore()
    profile = _probed(store, secrets, structured=False, generates=False)

    with pytest.raises(ModelProfileUnavailableError):
        store.activate(profile.profile_id, secrets)
