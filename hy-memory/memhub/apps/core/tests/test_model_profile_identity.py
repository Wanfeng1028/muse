"""Stable model editing and configured-vs-available credentials; no Keychain/network."""

import sqlite3

import pytest
from pydantic import SecretStr

from one_memory.model_profiles import (
    ModelCapabilities,
    ModelProfileConflictError,
    ModelProfileInput,
    ModelProfilePatch,
    ModelProfileStore,
    ModelProfileUnavailableError,
    ProviderKind,
)
from one_memory.secrets import InMemorySecretStore, SecretStoreUnavailableError


class MemorySecrets(InMemorySecretStore):
    unavailable = False

    def has(self, ref):
        if self.unavailable:
            raise SecretStoreUnavailableError("synthetic unavailable")
        return super().has(ref)


def setup_profile(tmp_path, *, with_key=True):
    store = ModelProfileStore(tmp_path / "model.sqlite3")
    secrets = MemorySecrets()
    profile = store.create(
        ModelProfileInput(
            name="Saved model",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            base_url="https://models.example/v1",
            model="model-1",
            api_key=SecretStr("synthetic-only") if with_key else None,
        ),
        secrets,
    )
    capabilities = ModelCapabilities(
        endpoint_reachable=True,
        model_available=True,
        embedding_available=True,
        structured_output=True,
    )
    store.record_capabilities(
        profile.profile_id,
        expected_revision=profile.revision,
        capabilities=capabilities,
        secrets=secrets,
    )
    return store, secrets, store.activate(profile.profile_id, secrets)


@pytest.mark.parametrize("state", ["available", "unavailable", "missing", "not-configured"])
def test_configured_key_is_stable_without_changing_availability_semantics(tmp_path, state):
    store, secrets, profile = setup_profile(tmp_path, with_key=state != "not-configured")
    if state == "unavailable":
        secrets.unavailable = True
    if state == "missing":
        secrets.delete(store.secret_ref(profile.profile_id))
    actual = store.require(profile.profile_id, secrets)
    assert actual.has_configured_api_key is (state != "not-configured")
    assert actual.has_api_key is (state == "available")
    assert actual.credential_state == ("missing" if state == "not-configured" else state)
    assert store.snapshot(profile.profile_id, 1).has_api_key is (state != "not-configured")
    assert "synthetic-only" not in actual.model_dump_json()
    assert "secret_ref" not in actual.model_dump_json()


@pytest.mark.parametrize("all_fields", [False, True])
def test_unchanged_save_preserves_revision_activation_capabilities_and_history(
    tmp_path, all_fields
):
    store, secrets, profile = setup_profile(tmp_path)
    fields = (
        {
            key: getattr(profile, key)
            for key in (
                "name",
                "base_url",
                "model",
                "embedding_model",
                "embedding_provider_kind",
                "embedding_base_url",
                "embedding_dimensions",
                "timeout_seconds",
                "max_concurrency",
                "context_window",
                "disable_thinking",
            )
        }
        if all_fields
        else {}
    )
    before = store.database_path.read_bytes()
    actual = store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, **fields), secrets
    )
    assert actual == profile
    assert store.snapshot(profile.profile_id, 1).profile_id == profile.profile_id
    with sqlite3.connect(store.database_path) as db:
        assert db.execute("SELECT COUNT(*) FROM model_profile_versions").fetchone()[0] == 1
    assert store.database_path.read_bytes() == before


@pytest.mark.parametrize(
    "change",
    [
        {"model": "model-2"},
        {"base_url": "https://other.example/v1"},
        {"api_key": SecretStr("replacement-only")},
    ],
)
def test_actual_edit_keeps_identity_but_requires_separate_test_and_activation(tmp_path, change):
    store, secrets, profile = setup_profile(tmp_path)
    updated = store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, **change), secrets
    )
    assert updated.profile_id == profile.profile_id and updated.revision == 2
    assert updated.is_active is False
    assert updated.capabilities == ModelCapabilities()
    assert updated.has_configured_api_key is True
    assert store.snapshot(profile.profile_id, 1).model == "model-1"
    with pytest.raises(ModelProfileUnavailableError, match="probe_required"):
        store.activate(profile.profile_id, secrets)
    with pytest.raises(ModelProfileConflictError):
        store.record_capabilities(
            profile.profile_id,
            expected_revision=1,
            capabilities=profile.capabilities,
            secrets=secrets,
        )
    probed = store.record_capabilities(
        profile.profile_id, expected_revision=2, capabilities=profile.capabilities, secrets=secrets
    )
    assert probed.is_active is False
    assert store.activate(profile.profile_id, secrets).is_active is True


def test_unchanged_stale_revision_cannot_bypass_cas(tmp_path):
    store, secrets, profile = setup_profile(tmp_path)
    store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, model="model-2"), secrets
    )
    with pytest.raises(ModelProfileConflictError):
        store.update(
            profile.profile_id, ModelProfilePatch(expected_revision=1, model="model-2"), secrets
        )


def test_noop_returns_same_revision_state_observed_inside_writer_transaction(tmp_path, monkeypatch):
    store, secrets, profile = setup_profile(tmp_path)
    require = store.require

    def concurrent_activation_change(profile_id, secret_store):
        observed = require(profile_id, secret_store)
        with sqlite3.connect(store.database_path) as writer:
            writer.execute(
                "UPDATE model_profiles SET is_active=0 WHERE profile_id=?", (profile_id,)
            )
        return observed

    monkeypatch.setattr(store, "require", concurrent_activation_change)
    unchanged = store.update(profile.profile_id, ModelProfilePatch(expected_revision=1), secrets)
    assert unchanged.revision == 1
    assert unchanged.is_active is False
    assert unchanged.capabilities == profile.capabilities


def test_clearing_a_key_updates_configured_presence_without_changing_identity(tmp_path):
    store, secrets, profile = setup_profile(tmp_path)
    cleared = store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, clear_api_key=True), secrets
    )
    assert cleared.profile_id == profile.profile_id and cleared.revision == 2
    assert not cleared.has_configured_api_key and not cleared.has_api_key
    assert cleared.credential_state == "missing"
    assert not cleared.is_active
    assert store.resolve_snapshot_secret(profile.profile_id, 1, secrets) is None


def test_unavailable_secret_does_not_block_noop_or_erase_reference(tmp_path):
    store, secrets, profile = setup_profile(tmp_path)
    secrets.unavailable = True
    current = store.require(profile.profile_id, secrets)
    updated = store.update(
        profile.profile_id, ModelProfilePatch(expected_revision=1, model=profile.model), secrets
    )
    assert updated == current
    assert updated.has_configured_api_key and not updated.has_api_key
    assert updated.credential_state == "unavailable"


def test_new_configuration_is_not_merged_just_because_endpoint_and_key_match(tmp_path):
    store, secrets, profile = setup_profile(tmp_path)
    other = store.create(
        ModelProfileInput(
            name=profile.name,
            provider_kind=profile.provider_kind,
            base_url=profile.base_url,
            model=profile.model,
            api_key=SecretStr("synthetic-only"),
        ),
        secrets,
    )
    assert other.profile_id != profile.profile_id
    assert other.revision == 1 and not other.is_active
    assert store.active_identity() == (profile.profile_id, profile.revision)


def test_failed_key_write_leaves_same_profile_revision_and_old_reference(tmp_path, monkeypatch):
    store, secrets, profile = setup_profile(tmp_path)
    reference = store.secret_ref(profile.profile_id)

    def reject(*_args):
        raise SecretStoreUnavailableError("synthetic failure")

    monkeypatch.setattr(secrets, "put", reject)
    with pytest.raises(SecretStoreUnavailableError):
        store.update(
            profile.profile_id,
            ModelProfilePatch(expected_revision=1, api_key=SecretStr("replacement")),
            secrets,
        )
    assert store.require(profile.profile_id, secrets) == profile
    assert store.secret_ref(profile.profile_id) == reference
