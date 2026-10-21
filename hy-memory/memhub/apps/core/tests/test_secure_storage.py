import json
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor

import pytest

from one_memory import secrets as secret_module
from one_memory.secrets import (
    KEYCHAIN_READ_BACKOFF_SECONDS,
    KEYCHAIN_READ_TIMEOUT,
    KEYCHAIN_WRITE_TIMEOUT,
    InMemorySecretStore,
    KeyringSecretStore,
    SecretStoreUnavailableError,
    keychain_service_name,
)


def test_isolated_keychain_service_namespace(monkeypatch):
    monkeypatch.setenv("ONE_MEMORY_TEST_ISOLATED", "1")
    monkeypatch.setenv("ONE_MEMORY_KEYCHAIN_SERVICE", "one-memory-qa-3779")
    assert keychain_service_name() == "one-memory-qa-3779"


def test_custom_keychain_service_is_refused_outside_isolated_tests(monkeypatch):
    monkeypatch.delenv("ONE_MEMORY_TEST_ISOLATED", raising=False)
    monkeypatch.setenv("ONE_MEMORY_KEYCHAIN_SERVICE", "one-memory-qa-3779")
    with pytest.raises(SecretStoreUnavailableError):
        keychain_service_name()


def test_packaged_keychain_budget_covers_loaded_process_startup():
    assert KEYCHAIN_READ_TIMEOUT >= 10
    assert KEYCHAIN_WRITE_TIMEOUT >= 15


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Security query")
def test_background_keychain_reads_refuse_interactive_authentication(monkeypatch):
    from keyring.backends.macOS import api

    captured = {}

    def query(**values):
        captured.update(values)
        return 1

    monkeypatch.setattr(api, "create_query", query)
    monkeypatch.setattr(api, "k_", lambda name: name)
    monkeypatch.setattr(
        api, "SecItemCopyMatching", lambda *_: api.error.sec_interaction_not_allowed
    )
    monkeypatch.setattr(api._found, "CFRelease", lambda *_: None)
    with pytest.raises(SecretStoreUnavailableError):
        secret_module._macos_password_without_prompt("test-reference")
    assert captured["kSecUseAuthenticationUI"] == "kSecUseAuthenticationUIFail"


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Security query")
def test_missing_keychain_entry_remains_absent_without_a_prompt(monkeypatch):
    from keyring.backends.macOS import api

    monkeypatch.setattr(api, "create_query", lambda **_: 1)
    monkeypatch.setattr(api, "k_", lambda name: name)
    monkeypatch.setattr(api, "SecItemCopyMatching", lambda *_: api.error.item_not_found)
    monkeypatch.setattr(api._found, "CFRelease", lambda *_: None)
    assert secret_module._macos_password_without_prompt("test-reference") is None


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain")
def test_keyring_resolve_uses_the_bounded_reader(monkeypatch):
    calls = []
    monkeypatch.setattr(
        secret_module, "_bounded_keychain_read", lambda ref: calls.append(ref) or None
    )
    assert KeyringSecretStore().resolve("missing") is None
    assert calls == ["missing"]


def test_keyring_resolve_caches_one_successful_read_in_memory(monkeypatch):
    calls = []
    backend = type("MacBackend", (), {"__module__": "keyring.backends.macOS"})()
    monkeypatch.setattr(secret_module._keyring(), "get_keyring", lambda: backend)
    monkeypatch.setattr(
        secret_module,
        "_bounded_keychain_read",
        lambda ref: calls.append(ref) or "cached-secret",
    )
    store = KeyringSecretStore()

    assert store.resolve("profile-ref") == "cached-secret"
    assert store.resolve("profile-ref") == "cached-secret"
    assert store.has("profile-ref")
    assert calls == ["profile-ref"]


def test_keyring_resolve_backs_off_after_denial_or_timeout(monkeypatch):
    """The penalty after a refusal is short, and capped.

    It used to be 60 / 300 / 900 seconds: three failures and every read was
    refused for fifteen minutes, which parked a queue of memory tasks behind
    one Keychain denial long after the user had allowed it.
    """
    calls = []
    now = [100.0]
    backend = type("MacBackend", (), {"__module__": "keyring.backends.macOS"})()
    monkeypatch.setattr(secret_module._keyring(), "get_keyring", lambda: backend)

    def unavailable(ref):
        calls.append((ref, now[0]))
        raise SecretStoreUnavailableError("authorization required")

    monkeypatch.setattr(secret_module, "_bounded_keychain_read", unavailable)
    store = KeyringSecretStore(clock=lambda: now[0])

    with pytest.raises(SecretStoreUnavailableError, match="authorization required"):
        store.resolve("profile-ref")
    # Each step's wait is served from backoff, then the next read is real
    # again: the penalty is a pause between attempts, not a refusal to try.
    for step in KEYCHAIN_READ_BACKOFF_SECONDS:
        now[0] += step - 0.1
        with pytest.raises(SecretStoreUnavailableError, match="backoff"):
            store.resolve("profile-ref")
        now[0] += 0.2
        with pytest.raises(SecretStoreUnavailableError, match="authorization required"):
            store.resolve("profile-ref")

    # However long the store keeps refusing, the wait stops growing: the ladder
    # is capped, so a store that recovers is not held behind an old penalty.
    ceiling = max(KEYCHAIN_READ_BACKOFF_SECONDS)
    before = len(calls)
    for _ in range(20):
        now[0] += ceiling
        with pytest.raises(SecretStoreUnavailableError, match="authorization required"):
            store.resolve("profile-ref")
    assert len(calls) - before == 20
    assert ceiling <= 30.0


def test_concurrent_keyring_resolves_share_one_child_read(monkeypatch):
    calls = []
    backend = type("MacBackend", (), {"__module__": "keyring.backends.macOS"})()
    monkeypatch.setattr(secret_module._keyring(), "get_keyring", lambda: backend)

    def read(ref):
        calls.append(ref)
        time.sleep(0.05)
        return "shared-secret"

    monkeypatch.setattr(secret_module, "_bounded_keychain_read", read)
    store = KeyringSecretStore()
    with ThreadPoolExecutor(max_workers=8) as executor:
        values = list(executor.map(store.resolve, ["profile-ref"] * 8))

    assert values == ["shared-secret"] * 8
    assert calls == ["profile-ref"]


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain")
def test_keyring_put_uses_the_bounded_writer(monkeypatch):
    calls = []
    monkeypatch.setattr(
        secret_module, "_bounded_keychain_write", lambda ref, value: calls.append((ref, value))
    )
    KeyringSecretStore().put("test-reference", "test-value")
    assert calls == [("test-reference", "test-value")]


def test_keychain_writer_uses_private_pipe_and_account_home(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, '{"stored": true}', "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(secret_module, "_keychain_environment", lambda: {"HOME": "/Users/account"})
    secret_module._bounded_keychain_write("private-reference", "private-value")
    command, args = calls[0]
    assert "private-reference" not in " ".join(command)
    assert "private-value" not in " ".join(command)
    assert json.loads(args["input"]) == {
        "reference": "private-reference",
        "value": "private-value",
    }
    assert args["env"]["HOME"] == "/Users/account"


def test_keychain_write_timeout_is_bounded(monkeypatch):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda *args, **kwargs: (_ for _ in ()).throw(
            subprocess.TimeoutExpired(args[0], kwargs["timeout"])
        ),
    )
    with pytest.raises(SecretStoreUnavailableError, match="timed out"):
        secret_module._bounded_keychain_write("private-reference", "private-value")


@pytest.mark.skipif(sys.platform != "darwin", reason="macOS Keychain")
def test_keyring_delete_uses_the_bounded_deleter(monkeypatch):
    calls = []
    monkeypatch.setattr(secret_module, "_bounded_keychain_delete", lambda ref: calls.append(ref))
    KeyringSecretStore().delete("test-reference")
    assert calls == ["test-reference"]


def test_keychain_delete_uses_private_pipe_and_account_home(monkeypatch):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, '{"deleted": true}', "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(secret_module, "_keychain_environment", lambda: {"HOME": "/Users/account"})
    secret_module._bounded_keychain_delete("private-reference")
    command, args = calls[0]
    assert "private-reference" not in " ".join(command)
    assert args["input"] == "private-reference"
    assert args["env"]["HOME"] == "/Users/account"


def test_keychain_bulk_delete_uses_one_bounded_private_pipe(monkeypatch):
    calls = []
    backend = type("MacBackend", (), {"__module__": "keyring.backends.macOS"})()
    monkeypatch.setattr(secret_module._keyring(), "get_keyring", lambda: backend)

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps({"deleted": 2}), "")

    monkeypatch.setattr(subprocess, "run", run)
    store = KeyringSecretStore()
    store.delete_many(("stale-1", "stale-2"))

    assert len(calls) == 1
    command, args = calls[0]
    assert command[-1] == "--many"
    assert json.loads(args["input"]) == {"references": ["stale-1", "stale-2"]}


def test_profiles_stay_editable_when_an_old_credential_requires_authorization(tmp_path):
    from pydantic import SecretStr

    from one_memory.model_profiles import (
        ModelProfileInput,
        ModelProfilePatch,
        ModelProfileStore,
        ProviderKind,
    )

    class SelectiveStore(InMemorySecretStore):
        denied = False

        def has(self, ref):
            if self.denied and self._values.get(ref) == "old-test-key":
                raise SecretStoreUnavailableError("authorization required")
            return super().has(ref)

    store = SelectiveStore()
    profiles = ModelProfileStore(tmp_path / "test.sqlite3")
    profile = profiles.create(
        ModelProfileInput(
            name="Test model",
            provider_kind=ProviderKind.OPENAI_COMPATIBLE,
            model="test",
            api_key=SecretStr("old-test-key"),
        ),
        store,
    )
    store.denied = True
    shown = profiles.list(store)[0]
    assert not shown.has_api_key and shown.credential_state == "unavailable"
    updated = profiles.update(
        profile.profile_id,
        ModelProfilePatch(expected_revision=1, api_key=SecretStr("new-test-key")),
        store,
    )
    assert updated.has_api_key and updated.credential_state == "available"


def test_keychain_subprocess_timeout_is_bounded_and_reaped(monkeypatch):
    children = []
    popen = subprocess.Popen

    def launch(*args, **kwargs):
        child = popen(*args, **kwargs)
        children.append(child)
        return child

    monkeypatch.setattr(subprocess, "Popen", launch)
    monkeypatch.setattr(secret_module, "KEYCHAIN_READ_TIMEOUT", 0.1, raising=False)
    monkeypatch.setattr(
        secret_module,
        "_keychain_read_command",
        lambda: [sys.executable, "-c", "import time; time.sleep(30)"],
        raising=False,
    )
    started = time.monotonic()
    with pytest.raises(SecretStoreUnavailableError, match="timed out"):
        secret_module._bounded_keychain_read("test-reference")
    assert time.monotonic() - started < 1
    assert len(children) == 1 and children[0].poll() is not None


@pytest.mark.parametrize("value", [None, "test-key<&>"])
def test_keychain_reader_uses_private_pipe_and_preserves_missing_value(monkeypatch, value):
    calls = []

    def run(command, **kwargs):
        calls.append((command, kwargs))
        return subprocess.CompletedProcess(command, 0, json.dumps({"value": value}), "")

    monkeypatch.setattr(subprocess, "run", run)
    monkeypatch.setattr(secret_module, "_keychain_environment", lambda: {"HOME": "/Users/account"})
    assert secret_module._bounded_keychain_read("private-reference") == value
    command, args = calls[0]
    assert "private-reference" not in " ".join(command)
    assert args["input"] == "private-reference"
    assert args["env"]["HOME"] == "/Users/account"
    assert args["capture_output"] and args["timeout"] > 0


@pytest.mark.parametrize(
    "returncode,output", [(1, "private-error"), (0, '{"value":42}'), (0, "invalid")]
)
def test_keychain_reader_failure_never_leaks_output(monkeypatch, returncode, output):
    monkeypatch.setattr(
        subprocess,
        "run",
        lambda command, **kwargs: subprocess.CompletedProcess(
            command, returncode, output, "secret-details"
        ),
    )
    with pytest.raises(SecretStoreUnavailableError) as error:
        secret_module._bounded_keychain_read("private-reference")
    assert "private" not in str(error.value) and "secret-details" not in str(error.value)


def test_a_fresh_interpreter_can_resolve_with_a_stubbed_backend(tmp_path):
    """Importing `secrets` must be enough; resolving must work.

    B made `keyring` a lazy import so the Reader does not load the
    secure-storage stack. Four call sites kept reaching for the module-level
    name, which is `None` until first use — so a fresh process that had only
    imported the module raised `AttributeError` instead of reading, and the
    `except` clause could not catch it because it is not a keyring error.

    Runs in a child interpreter because the whole point is what a process
    sees before anything else has touched the module.
    """
    import subprocess
    import sys
    import textwrap

    program = textwrap.dedent(
        """
        import sys, types
        import one_memory.secrets as secrets

        class Backend:
            __module__ = "keyring.backends.fail"
            def get_password(self, service, ref):
                return "stubbed-value"
            def set_password(self, service, ref, value):
                return None

        kr = secrets._keyring()
        assert kr is not None, "the lazy import returned nothing"
        kr.get_keyring = lambda: Backend()
        kr.get_password = lambda service, ref: "stubbed-value"
        store = secrets.KeyringSecretStore()
        assert store.resolve("anything") == "stubbed-value"
        print("ok")
        """
    )
    result = subprocess.run(
        [sys.executable, "-c", program],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "ok" in result.stdout
