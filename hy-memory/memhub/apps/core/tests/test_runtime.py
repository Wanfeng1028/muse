import json
import os
import stat
import subprocess
import sys
import time

import pytest

from one_memory.config import Settings
from one_memory.runtime import CoreAlreadyRunningError, CoreRuntime


def test_runtime_writes_and_removes_ownership_receipt(tmp_path) -> None:
    settings = Settings(
        data_dir=tmp_path,
        host="127.0.0.1",
        port=9876,
        instance_id="owned-instance",
    )

    with CoreRuntime(settings):
        receipt = json.loads((tmp_path / "runtime.json").read_text(encoding="utf-8"))
        assert receipt["schema_version"] == 1
        assert receipt["service"] == "one-memory-core"
        assert receipt["instance_id"] == "owned-instance"
        assert receipt["host"] == "127.0.0.1"
        assert receipt["port"] == 9876
        assert "api_token" not in receipt
        assert (tmp_path / "runtime-token").read_text(encoding="utf-8") == (
            settings.api_token.get_secret_value()
        )
        if os.name == "posix":
            assert stat.S_IMODE((tmp_path / "runtime-token").stat().st_mode) == 0o600

    assert not (tmp_path / "runtime.json").exists()
    assert not (tmp_path / "runtime-token").exists()


def test_runtime_rejects_second_owner_for_same_data_directory(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, instance_id="first")

    with (
        CoreRuntime(settings),
        pytest.raises(CoreAlreadyRunningError),
        CoreRuntime(Settings(data_dir=tmp_path, instance_id="second")),
    ):
        raise AssertionError("second owner must not start")


def test_nonpublishing_maintenance_owner_still_excludes_a_second_core(tmp_path) -> None:
    settings = Settings(data_dir=tmp_path, instance_id="maintenance")

    with CoreRuntime(settings, publish_receipt=False):
        assert not (tmp_path / "runtime.json").exists()
        assert not (tmp_path / "runtime-token").exists()
        with (
            pytest.raises(CoreAlreadyRunningError),
            CoreRuntime(Settings(data_dir=tmp_path, instance_id="second")),
        ):
            raise AssertionError("second owner must not start")


def test_core_lock_excludes_a_second_process_for_the_same_data_directory(tmp_path) -> None:
    ready = tmp_path / "ready"
    child = subprocess.Popen(
        [
            sys.executable,
            "-c",
            (
                "import time; from pathlib import Path; "
                "from one_memory.config import Settings; "
                "from one_memory.runtime import CoreRuntime; "
                f"root=Path({str(tmp_path)!r}); ready=Path({str(ready)!r}); "
                "\nwith CoreRuntime(Settings(data_dir=root, instance_id='child'), "
                "publish_receipt=False):\n ready.write_text('ready'); time.sleep(10)"
            ),
        ],
        env={**os.environ},
    )
    try:
        deadline = time.monotonic() + 5
        while not ready.exists() and child.poll() is None and time.monotonic() < deadline:
            time.sleep(0.02)
        assert ready.exists(), f"child failed before locking: {child.poll()}"
        with (
            pytest.raises(CoreAlreadyRunningError),
            CoreRuntime(Settings(data_dir=tmp_path, instance_id="parent")),
        ):
            raise AssertionError("second process must not start")
    finally:
        child.terminate()
        child.wait(timeout=5)

    with CoreRuntime(Settings(data_dir=tmp_path, instance_id="after-child"), publish_receipt=False):
        pass
