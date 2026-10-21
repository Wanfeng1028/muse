import sqlite3
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from threading import Event
from uuid import uuid4

import pytest
from pydantic import SecretStr, ValidationError

from one_memory.model_profiles import (
    ModelCreationOperationConflictError,
    ModelCreationOperationLookupError,
    ModelProfileInput,
    ModelProfilePatch,
    ModelProfileStore,
)
from one_memory.secrets import InMemorySecretStore, SecretStoreUnavailableError

TABLE = "model_profile_creation_operations"


def model(operation_id=None, **changes):
    return ModelProfileInput(
        **{
            "name": "Synthetic name",
            "provider_kind": "openai_compatible",
            "base_url": "https://fixture.invalid/v1",
            "model": "synthetic-model",
            "api_key": SecretStr("synthetic-key-not-real"),
            "creation_operation_id": operation_id,
            **changes,
        }
    )


@pytest.fixture
def env(tmp_path):
    return ModelProfileStore(tmp_path / "models.sqlite3"), InMemorySecretStore()


def dump(store):
    with closing(sqlite3.connect(store.database_path)) as db:
        return tuple(db.iterdump())


def test_lookup_without_table_is_read_only_and_legacy_create_does_not_initialize(env):
    store, secrets = env
    first = store.create(model(), secrets)
    second = store.create(model(), secrets)
    assert first.profile_id != second.profile_id
    operation_id = str(uuid4())
    before = dump(store)
    assert store.lookup_creation_operation(operation_id) == {
        "operation_id": operation_id,
        "state": "not_found",
        "profile_id": None,
        "created_revision": None,
    }
    assert dump(store) == before
    with closing(sqlite3.connect(store.database_path)) as db:
        assert db.execute("SELECT 1 FROM sqlite_master WHERE name=?", (TABLE,)).fetchone() is None


def test_operation_commits_with_profile_and_version_without_autoactivation(env):
    store, secrets = env
    operation_id = str(uuid4())
    profile = store.create(model(operation_id), secrets)
    assert profile.revision == 1 and not profile.is_active
    assert store.lookup_creation_operation(operation_id) == {
        "operation_id": operation_id,
        "state": "committed",
        "profile_id": profile.profile_id,
        "created_revision": 1,
    }
    assert store.snapshot(profile.profile_id, 1).profile_id == profile.profile_id
    assert store.active_identity() is None


@pytest.mark.parametrize("change", [{}, {"name": "another name"}, {"api_key": "different-key"}])
def test_any_replay_conflicts_before_secret_put(env, monkeypatch, change):
    store, secrets = env
    operation_id = str(uuid4())
    original = store.create(model(operation_id), secrets)
    monkeypatch.setattr(secrets, "put", lambda *args: pytest.fail("duplicate secret write"))
    with pytest.raises(
        ModelCreationOperationConflictError, match="^model_creation_operation_conflict$"
    ):
        store.create(model(operation_id, **change), secrets)
    assert [item.profile_id for item in store.list(secrets)] == [original.profile_id]


def test_reservation_is_committed_before_secret_put_failure_and_remains_pending(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())
    observed = []

    def fail_put(ref, value):
        lookup = store.lookup_creation_operation(operation_id)
        observed.append(lookup)
        assert lookup["state"] == "pending"
        assert ref == f"model-profile:{lookup['profile_id']}"
        assert value == "synthetic-key-not-real"
        raise SecretStoreUnavailableError("simulated unavailable")

    monkeypatch.setattr(secrets, "put", fail_put)
    with pytest.raises(SecretStoreUnavailableError):
        store.create(model(operation_id), secrets)
    assert len(observed) == 1
    assert store.lookup_creation_operation(operation_id) == observed[0]
    assert store.list(secrets) == []
    with pytest.raises(ModelCreationOperationConflictError):
        store.create(model(operation_id), secrets)
    assert len(observed) == 1


def test_pending_creation_can_be_explicitly_abandoned(env) -> None:
    store, _secrets = env
    operation_id = str(uuid4())
    profile_id = str(uuid4())
    store._reserve_creation_operation(operation_id, profile_id)

    assert store.abandon_creation_operation(operation_id) == {
        "operation_id": operation_id,
        "state": "deleted",
        "profile_id": profile_id,
        "created_revision": 1,
    }
    assert store.lookup_creation_operation(operation_id)["state"] == "not_found"


def test_abandon_wins_against_an_inflight_create_without_leaving_a_profile(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())
    entered, release = Event(), Event()
    put = secrets.put

    def hold_put(ref, value):
        entered.set()
        assert release.wait(5)
        put(ref, value)

    monkeypatch.setattr(secrets, "put", hold_put)
    with ThreadPoolExecutor(max_workers=1) as pool:
        creating = pool.submit(store.create, model(operation_id), secrets)
        assert entered.wait(5)
        assert store.abandon_creation_operation(operation_id)["state"] == "deleted"
        release.set()
        with pytest.raises(ModelCreationOperationLookupError):
            creating.result(timeout=5)

    assert store.list(secrets) == []
    assert store.lookup_creation_operation(operation_id)["state"] == "not_found"


def test_interrupted_secret_write_is_not_retried_or_marked_committed(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())

    def interrupted(*args):
        raise KeyboardInterrupt

    monkeypatch.setattr(secrets, "put", interrupted)
    with pytest.raises(KeyboardInterrupt):
        store.create(model(operation_id), secrets)
    assert store.lookup_creation_operation(operation_id)["state"] == "pending"
    with pytest.raises(ModelCreationOperationConflictError):
        store.create(model(operation_id), secrets)


def test_insert_failure_preserves_pending_and_existing_secret_compensation(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())

    def failed_version(*args):
        raise sqlite3.OperationalError("version write failed")

    monkeypatch.setattr(store, "_insert_current_version", failed_version)
    with pytest.raises(sqlite3.OperationalError, match="version write failed"):
        store.create(model(operation_id), secrets)
    lookup = store.lookup_creation_operation(operation_id)
    assert lookup["state"] == "pending"
    assert not secrets.has(f"model-profile:{lookup['profile_id']}")
    assert store.list(secrets) == []
    with closing(sqlite3.connect(store.database_path)) as db:
        assert db.execute("SELECT COUNT(*) FROM model_profile_versions").fetchone()[0] == 0


def test_operation_commit_failure_rolls_back_profile_and_version(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())
    put = secrets.put

    def fail_commit(ref, value):
        put(ref, value)
        with sqlite3.connect(store.database_path) as db:
            db.execute(f"""CREATE TRIGGER refuse_commit BEFORE UPDATE ON {TABLE}
                BEGIN SELECT RAISE(ABORT, 'simulated failure'); END""")

    monkeypatch.setattr(secrets, "put", fail_commit)
    with pytest.raises(sqlite3.Error):
        store.create(model(operation_id), secrets)
    lookup = store.lookup_creation_operation(operation_id)
    assert lookup["state"] == "pending" and store.list(secrets) == []
    assert not secrets.has(f"model-profile:{lookup['profile_id']}:revision:1")


def test_postcommit_response_read_failure_is_recoverable_without_recreating(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())
    require = store.require
    monkeypatch.setattr(
        store, "require", lambda *args: (_ for _ in ()).throw(RuntimeError("lost read"))
    )
    with pytest.raises(RuntimeError, match="lost read"):
        store.create(model(operation_id), secrets)
    lookup = store.lookup_creation_operation(operation_id)
    assert lookup["state"] == "committed"
    assert secrets.has(f"model-profile:{lookup['profile_id']}")
    monkeypatch.setattr(store, "require", require)
    reopened = ModelProfileStore(store.database_path)
    assert reopened.lookup_creation_operation(operation_id) == lookup
    with pytest.raises(ModelCreationOperationConflictError):
        reopened.create(model(operation_id), secrets)
    assert len(reopened.list(secrets)) == 1


def test_same_operation_concurrent_create_only_one_secret_write_and_profile(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())
    entered, release = Event(), Event()
    calls = []
    put = secrets.put

    def hold_put(ref, value):
        calls.append(ref)
        entered.set()
        assert release.wait(5)
        put(ref, value)

    monkeypatch.setattr(secrets, "put", hold_put)
    with ThreadPoolExecutor(max_workers=2) as pool:
        first = pool.submit(store.create, model(operation_id), secrets)
        try:
            assert entered.wait(5)
            second = pool.submit(store.create, model(operation_id), secrets)
            with pytest.raises(ModelCreationOperationConflictError):
                second.result(timeout=5)
        finally:
            release.set()
        created = first.result(timeout=5)
    assert len(calls) == 1
    assert store.lookup_creation_operation(operation_id)["profile_id"] == created.profile_id
    assert len(store.list(secrets)) == 1


def test_lookup_after_edit_or_delete_keeps_original_creation_identity(env):
    store, secrets = env
    operation_id = str(uuid4())
    created = store.create(model(operation_id), secrets)
    store.update(created.profile_id, ModelProfilePatch(expected_revision=1, name="edited"), secrets)
    assert store.lookup_creation_operation(operation_id)["created_revision"] == 1
    store.delete(created.profile_id, secrets)
    assert store.lookup_creation_operation(operation_id) == {
        "operation_id": operation_id,
        "state": "deleted",
        "profile_id": created.profile_id,
        "created_revision": 1,
    }
    with pytest.raises(ModelCreationOperationConflictError):
        store.create(model(operation_id), secrets)


def test_operation_table_contains_only_nonsecret_identity(env):
    store, secrets = env
    operation_id = str(uuid4())
    store.create(model(operation_id), secrets)
    with closing(sqlite3.connect(store.database_path)) as db:
        columns = [row[1] for row in db.execute(f"PRAGMA table_info({TABLE})")]
        rows = db.execute(f"SELECT * FROM {TABLE}").fetchall()
    assert set(columns) == {"operation_id", "profile_id", "state", "created_revision"}
    for excluded in (
        "synthetic-key-not-real",
        "fixture.invalid",
        "Synthetic name",
        "synthetic-model",
    ):
        assert excluded not in repr(rows)


@pytest.mark.parametrize(
    "operation_id",
    [
        "not-uuid",
        "a" * 32,
        "ABCDEFAB-CDEF-ABCD-EFAB-CDEFABCDEFAB",
        "{abcdefab-cdef-abcd-efab-cdefabcdefab}",
        1,
    ],
)
def test_noncanonical_input_and_lookup_rejected(env, operation_id):
    store, _ = env
    with pytest.raises(ValidationError):
        model(operation_id)
    with pytest.raises(ValueError, match="invalid_creation_operation_id"):
        store.lookup_creation_operation(operation_id)


@pytest.mark.parametrize(
    "column,value", [("profile_id", "invalid"), ("state", "other"), ("created_revision", 2)]
)
def test_corrupt_stored_row_fails_closed_with_fixed_error(env, column, value):
    store, secrets = env
    operation_id = str(uuid4())
    store.create(model(operation_id), secrets)
    with sqlite3.connect(store.database_path) as db:
        db.execute("PRAGMA ignore_check_constraints=ON")
        db.execute(f"UPDATE {TABLE} SET {column}=?", (value,))
    with pytest.raises(
        ModelCreationOperationLookupError, match="^model_creation_operation_lookup_unavailable$"
    ):
        store.lookup_creation_operation(operation_id)


def test_broken_table_lookup_and_create_fail_before_secret_write(env, monkeypatch):
    store, secrets = env
    with sqlite3.connect(store.database_path) as db:
        db.execute(f"CREATE TABLE {TABLE}(unexpected TEXT)")
    monkeypatch.setattr(
        secrets, "put", lambda *args: pytest.fail("unsafe store cannot write secret")
    )
    with pytest.raises(ModelCreationOperationLookupError):
        store.lookup_creation_operation(str(uuid4()))
    with pytest.raises(ModelCreationOperationLookupError):
        store.create(model(str(uuid4())), secrets)


def test_creation_operation_lookup_never_creates_a_missing_database(env, tmp_path):
    store, _ = env
    store.database_path = tmp_path / "missing.sqlite3"
    with pytest.raises(ModelCreationOperationLookupError):
        store.lookup_creation_operation(str(uuid4()))
    assert not store.database_path.exists()


def test_reopened_pending_operation_never_reenters_secret_write(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())
    monkeypatch.setattr(
        secrets, "put", lambda *args: (_ for _ in ()).throw(SecretStoreUnavailableError())
    )
    with pytest.raises(SecretStoreUnavailableError):
        store.create(model(operation_id), secrets)
    pending = store.lookup_creation_operation(operation_id)
    reopened = ModelProfileStore(store.database_path)
    monkeypatch.setattr(secrets, "put", lambda *args: pytest.fail("pending cannot retry"))
    assert reopened.lookup_creation_operation(operation_id) == pending
    with pytest.raises(ModelCreationOperationConflictError):
        reopened.create(model(operation_id), secrets)


def test_read_connection_is_query_only_and_lookup_does_not_consult_secrets(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())
    store.create(model(operation_id), secrets)
    before = dump(store)
    for method in ("has", "resolve", "put", "delete"):
        monkeypatch.setattr(secrets, method, lambda *args: pytest.fail("lookup touched secret"))
    assert store.lookup_creation_operation(operation_id)["state"] == "committed"
    with store._creation_connection() as db:
        assert db.in_transaction
        with pytest.raises(sqlite3.OperationalError, match="readonly"):
            db.execute(f"DELETE FROM {TABLE}")
    assert dump(store) == before


def test_keyless_operation_commits_without_secret_write(env, monkeypatch):
    store, secrets = env
    operation_id = str(uuid4())
    monkeypatch.setattr(secrets, "put", lambda *args: pytest.fail("keyless create wrote secret"))
    profile = store.create(
        model(
            operation_id, provider_kind="ollama", base_url="http://127.0.0.1:11434", api_key=None
        ),
        secrets,
    )
    assert store.lookup_creation_operation(operation_id)["profile_id"] == profile.profile_id
    assert store.lookup_creation_operation(operation_id)["state"] == "committed"


def test_corrupt_database_returns_fixed_lookup_error(env, tmp_path):
    store, _ = env
    database = tmp_path / "corrupt.sqlite3"
    database.write_bytes(b"not a database containing secret-like text")
    store.database_path = database
    with pytest.raises(
        ModelCreationOperationLookupError, match="^model_creation_operation_lookup_unavailable$"
    ):
        store.lookup_creation_operation(str(uuid4()))
