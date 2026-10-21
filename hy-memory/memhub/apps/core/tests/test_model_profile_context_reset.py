import asyncio
import sqlite3
from contextlib import closing

import pytest
from httpx import ASGITransport, AsyncClient
from pydantic import SecretStr, ValidationError

from one_memory.api import create_app
from one_memory.config import Settings
from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileConflictError,
    ModelProfileInput,
    ModelProfilePatch,
    ModelProfileStore,
    ProviderKind,
)
from one_memory.secrets import InMemorySecretStore, SecretStoreUnavailableError


class MemorySecrets(InMemorySecretStore):
    def __init__(self):
        super().__init__()
        self.writes = []
        self.unavailable = False

    def put(self, ref, value):
        self.writes.append(("put", ref))
        super().put(ref, value)

    def delete(self, ref):
        self.writes.append(("delete", ref))
        super().delete(ref)

    def has(self, ref):
        if self.unavailable:
            raise SecretStoreUnavailableError("synthetic unavailable")
        return super().has(ref)


@pytest.fixture
def store_and_secrets(tmp_path):
    return ModelProfileStore(tmp_path / "profiles.sqlite3"), MemorySecrets()


def create(store, secrets, **fields):
    return store.create(
        ModelProfileInput(
            name="Synthetic profile",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model="synthetic-model",
            api_key=SecretStr("synthetic-context-key"),
            **fields,
        ),
        secrets,
    )


def versions(store, profile_id):
    with closing(sqlite3.connect(store.database_path)) as db:
        return db.execute(
            "SELECT revision, context_window, secret_ref FROM model_profile_versions "
            "WHERE profile_id=? ORDER BY revision",
            (profile_id,),
        ).fetchall()


@pytest.mark.parametrize(
    "fields, expected",
    [
        ({}, None),
        ({"context_window": None}, None),
        ({"context_window": 1024}, 1024),
        ({"context_window": 32768}, 32768),
        ({"context_window": 10_000_000}, 10_000_000),
    ],
)
def test_create_context_default_and_inclusive_bounds(store_and_secrets, fields, expected):
    store, secrets = store_and_secrets
    profile = create(store, secrets, **fields)
    assert profile.context_window == expected
    assert store.require(profile.profile_id, secrets).context_window == expected
    assert store.snapshot(profile.profile_id, 1).context_window == expected
    assert profile.revision == 1


def test_explicit_null_clears_override_and_preserves_history_and_secret(store_and_secrets):
    store, secrets = store_and_secrets
    profile = create(store, secrets, context_window=32768)
    ref = store.secret_ref(profile.profile_id)
    writes = list(secrets.writes)
    patch = ModelProfilePatch.model_validate_json('{"expected_revision":1,"context_window":null}')
    assert "context_window" in patch.model_fields_set
    updated = store.update(profile.profile_id, patch, secrets)
    assert updated.context_window is None
    assert updated.revision == 2
    assert store.require(profile.profile_id, secrets) == updated
    assert versions(store, profile.profile_id) == [(1, 32768, ref), (2, None, ref)]
    assert store.snapshot(profile.profile_id, 1).context_window == 32768
    assert store.snapshot(profile.profile_id, 2).context_window is None
    with closing(sqlite3.connect(store.database_path)) as db:
        assert (
            db.execute(
                "SELECT context_window IS NULL FROM model_profiles WHERE profile_id=?",
                (profile.profile_id,),
            ).fetchone()[0]
            == 1
        )
    assert store.secret_ref(profile.profile_id) == ref
    assert secrets.writes == writes
    assert secrets.resolve(ref) == "synthetic-context-key"
    assert "synthetic-context-key" not in updated.model_dump_json()
    assert b"synthetic-context-key" not in store.database_path.read_bytes()
    unchanged_fields = set(type(profile).model_fields) - {
        "context_window",
        "revision",
        "updated_at",
    }
    assert all(getattr(profile, key) == getattr(updated, key) for key in unchanged_fields)


@pytest.mark.parametrize(
    "initial, fields",
    [
        (32768, {}),
        (32768, {"context_window": 32768}),
        (None, {}),
        (None, {"context_window": None}),
    ],
)
def test_omitted_or_same_value_is_noop_with_unchanged_revision_and_metadata(
    store_and_secrets, initial, fields
):
    store, secrets = store_and_secrets
    profile = create(store, secrets, context_window=initial)
    store.record_capabilities(
        profile.profile_id,
        expected_revision=1,
        secrets=secrets,
        capabilities=ModelCapabilities(endpoint_reachable=True, model_available=True),
    )
    profile = store.require(profile.profile_id, secrets)
    before = store.database_path.read_bytes()
    writes = list(secrets.writes)
    patch = ModelProfilePatch(expected_revision=1, **fields)
    assert ("context_window" in patch.model_fields_set) == ("context_window" in fields)
    assert store.update(profile.profile_id, patch, secrets) == profile
    assert store.database_path.read_bytes() == before
    assert len(versions(store, profile.profile_id)) == 1
    assert secrets.writes == writes


def test_unrelated_update_omits_context_and_preserves_override(store_and_secrets):
    store, secrets = store_and_secrets
    profile = create(store, secrets, context_window=32768)
    patch = ModelProfilePatch.model_validate_json('{"expected_revision":1,"name":"Renamed"}')
    updated = store.update(profile.profile_id, patch, secrets)
    assert updated.context_window == 32768
    assert updated.name == "Renamed" and updated.revision == 2


@pytest.mark.parametrize("value", [1024, 65536, 10_000_000])
def test_explicit_value_sets_override_from_default(store_and_secrets, value):
    store, secrets = store_and_secrets
    profile = create(store, secrets)
    updated = store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, context_window=value), secrets
    )
    assert updated.context_window == value and updated.revision == 2
    assert store.snapshot(profile.profile_id, 1).context_window is None
    assert store.snapshot(profile.profile_id, 2).context_window == value


def test_reset_retry_is_noop_only_with_current_revision(store_and_secrets):
    store, secrets = store_and_secrets
    profile = create(store, secrets, context_window=32768)
    reset = store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, context_window=None), secrets
    )
    assert reset.revision == 2
    before = store.database_path.read_bytes()
    assert (
        store.update(
            profile.profile_id, ModelProfilePatch(expected_revision=2, context_window=None), secrets
        )
        == reset
    )
    with pytest.raises(ModelProfileConflictError):
        store.update(
            profile.profile_id, ModelProfilePatch(expected_revision=1, context_window=None), secrets
        )
    assert store.database_path.read_bytes() == before
    assert len(versions(store, profile.profile_id)) == 2


@pytest.mark.parametrize("fields", [{}, {"context_window": None}, {"context_window": 32768}])
def test_unknown_and_stale_revision_do_not_write(store_and_secrets, fields):
    store, secrets = store_and_secrets
    profile = create(store, secrets, context_window=32768)
    before = store.database_path.read_bytes()
    writes = list(secrets.writes)
    with pytest.raises(KeyError):
        store.update("unknown", ModelProfilePatch(expected_revision=1, **fields), secrets)
    with pytest.raises(ModelProfileConflictError):
        store.update(profile.profile_id, ModelProfilePatch(expected_revision=99, **fields), secrets)
    assert store.require(profile.profile_id, secrets) == profile
    assert store.database_path.read_bytes() == before
    assert secrets.writes == writes


@pytest.mark.parametrize(
    "value", [0, -1, 1023, 10_000_001, 1024.5, "", "not-a-number", True, False, [], {}]
)
@pytest.mark.parametrize("kind", ["create", "update"])
def test_invalid_context_is_rejected_without_writes(store_and_secrets, kind, value):
    store, secrets = store_and_secrets
    profile = create(store, secrets, context_window=32768)
    before = store.database_path.read_bytes()
    writes = list(secrets.writes)
    with pytest.raises(ValidationError):
        if kind == "create":
            create(store, secrets, context_window=value)
        else:
            store.update(
                profile.profile_id,
                ModelProfilePatch(expected_revision=1, context_window=value),
                secrets,
            )
    assert store.database_path.read_bytes() == before
    assert secrets.writes == writes


@pytest.mark.parametrize("value", ["32768", 32768.0])
def test_existing_integral_coercion_is_unchanged(value):
    assert ModelProfilePatch(expected_revision=1, context_window=value).context_window == 32768
    assert (
        ModelProfileInput(
            name="Synthetic", provider_kind=ProviderKind.OLLAMA, model="test", context_window=value
        ).context_window
        == 32768
    )


def test_reset_does_not_touch_keys_or_change_existing_activation_policy(store_and_secrets):
    store, secrets = store_and_secrets
    profile = create(store, secrets, context_window=32768)
    with closing(sqlite3.connect(store.database_path)) as db, db:
        db.execute("UPDATE model_profiles SET is_active=1, endpoint_reachable=1, model_available=1")
    secrets.unavailable = True
    writes = list(secrets.writes)
    updated = store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, context_window=None), secrets
    )
    assert updated.context_window is None and updated.revision == 2
    assert updated.is_active is True  # Context edits are not in the existing deactivation set.
    assert updated.capabilities == ModelCapabilities()
    assert updated.has_configured_api_key and updated.credential_state == "unavailable"
    assert secrets.writes == writes


def test_existing_patch_route_preserves_json_omission_and_explicit_null(
    store_and_secrets, tmp_path
):
    store, secrets = store_and_secrets
    profile = create(store, secrets, context_window=32768)
    app = create_app(
        Settings(
            data_dir=tmp_path / "unused",
            source_home=tmp_path,
            api_token=SecretStr("synthetic-token"),
            automatic_memory_processing=False,
            live_sync_enabled=False,
        ),
        secret_store=secrets,
        source_catalog={},
    )
    # Do not start Runtime, scan sources or probe a model for this HTTP binding check.
    app.state.model_profile_store = store
    app.state.secret_store = secrets

    async def run():
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": "Bearer synthetic-token"},
        ) as client:
            url = f"/api/v1/model-profiles/{profile.profile_id}"
            omitted = await client.patch(url, json={"expected_revision": 1})
            assert omitted.status_code == 200
            assert omitted.json()["context_window"] == 32768
            reset = await client.patch(url, json={"expected_revision": 1, "context_window": None})
            assert reset.status_code == 200
            assert reset.json()["context_window"] is None and reset.json()["revision"] == 2
            stale = await client.patch(url, json={"expected_revision": 1, "context_window": None})
            assert stale.status_code == 409
            invalid = await client.patch(url, json={"expected_revision": 2, "context_window": 0})
            assert invalid.status_code == 422

    asyncio.run(run())
