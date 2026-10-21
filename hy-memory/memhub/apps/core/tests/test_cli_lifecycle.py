import os
import socket
import subprocess
import sys
import time

import httpx

from one_memory.http_client import create_client


def reserve_port() -> int:
    with socket.socket() as listener:
        listener.bind(("127.0.0.1", 0))
        return int(listener.getsockname()[1])


def test_cli_starts_and_stops_without_residual_runtime(tmp_path) -> None:
    port = reserve_port()
    environment = {
        **os.environ,
        "ONE_MEMORY_DATA_DIR": str(tmp_path),
        "ONE_MEMORY_PORT": str(port),
        "ONE_MEMORY_INSTANCE_ID": "cli-lifecycle-test",
    }
    process = subprocess.Popen(
        [sys.executable, "-m", "one_memory.cli"],
        env=environment,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
        text=True,
    )

    try:
        health: dict[str, object] | None = None
        for _ in range(50):
            if process.poll() is not None:
                error = process.stderr.read() if process.stderr else ""
                raise AssertionError(f"Core exited before ready: {error}")
            try:
                with create_client(timeout=0.2) as client:
                    health = client.get(
                        f"http://127.0.0.1:{port}/api/v1/health",
                    ).json()
                break
            except httpx.HTTPError:
                time.sleep(0.1)

        assert health is not None
        assert health["instance_id"] == "cli-lifecycle-test"
        assert (tmp_path / "runtime.json").exists()
        assert (tmp_path / "runtime-token").exists()
    finally:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=5)

    assert not (tmp_path / "runtime.json").exists()
    assert not (tmp_path / "runtime-token").exists()
    with socket.socket() as client:
        assert client.connect_ex(("127.0.0.1", port)) != 0
