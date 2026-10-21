"""Split packaged recall latency into CLI subprocess vs Core HTTP time.

The peak replay probe deliberately measures the packaged CLI end to end, which
includes process startup. That is the right user-facing boundary, but it does
not say whether a latency spike belongs to the CLI wrapper or Core's recall
handler. This probe uses the same isolated Runtime and compares:

1. `one-memory recall ... --json` subprocess wall time;
2. the same query through Core HTTP from Python.

It does not modify the source tree, daily `~/.one-memory`, or a real host source.
"""

from __future__ import annotations

import argparse
import json
import os
import shutil
import socket
import statistics
import subprocess
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def _run(cli: Path, args: list[str], env: dict[str, str]) -> subprocess.CompletedProcess:
    return subprocess.run(
        [str(cli), *args],
        env=env,
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
    )


def _json(text: str) -> dict:
    try:
        value = json.loads(text)
    except (TypeError, ValueError):
        return {}
    return value if isinstance(value, dict) else {}


def _stats(values: list[float]) -> dict:
    if not values:
        return {}
    ordered = sorted(values)
    return {
        "samples": len(ordered),
        "p50_ms": round(statistics.median(ordered) * 1000, 1),
        "p95_ms": round(ordered[min(len(ordered) - 1, int(len(ordered) * 0.95))] * 1000, 1),
        "max_ms": round(max(ordered) * 1000, 1),
    }


def _http_recall(port: int, token: str, query: str) -> float:
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/v1/recall",
        data=json.dumps({"query": query, "scope": "all-apps", "limit": 8}).encode(),
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )
    started = time.perf_counter()
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            if response.status != 200:
                raise RuntimeError(f"recall_status_{response.status}")
            response.read()
    except urllib.error.HTTPError as error:
        raise RuntimeError(f"recall_status_{error.code}") from None
    return time.perf_counter() - started


def _wait_for_http(port: int, token: str, *, timeout: float = 15.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            _http_recall(port, token, "__om_probe__")
            return True
        except (OSError, RuntimeError):
            time.sleep(0.1)
    return False


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--package", required=True)
    parser.add_argument("--samples", type=int, default=20)
    parser.add_argument("--interval", type=float, default=0.05)
    args = parser.parse_args()

    package = Path(args.package).resolve()
    cli = package / "artifacts/runtime-dist/bin/one-memory"
    if not cli.exists():
        print(json.dumps({"state": "blocked", "reason": "cli_missing", "cli": str(cli)}))
        return 2

    work = Path(tempfile.mkdtemp(prefix="c1-recall-stage-"))
    home = work / "home"
    data = work / "data"
    home.mkdir()
    data.mkdir()
    port = _free_port()
    token = "stage-probe-token"
    env = dict(os.environ)
    env.update(
        {
            "ONE_MEMORY_DATA_DIR": str(data),
            "ONE_MEMORY_SOURCE_HOME": str(home),
            "ONE_MEMORY_HOST_HOME": str(home),
            "ONE_MEMORY_PORT": str(port),
            "ONE_MEMORY_API_TOKEN": token,
            "ONE_MEMORY_AUTOMATIC_MEMORY_PROCESSING": "false",
            "ONE_MEMORY_LIVE_SYNC_ENABLED": "false",
        }
    )
    receipt: dict = {"schema_version": 1, "package": package.name, "samples": args.samples}
    process = None
    try:
        process = subprocess.Popen(
            [str(cli), "serve"],
            env=env,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
        )
        ready = {}
        for _ in range(120):
            ready = _json(_run(cli, ["status", "--json"], env).stdout)
            if ready.get("runtime", {}).get("state") == "running":
                break
            time.sleep(0.5)
        receipt["runtime"] = ready.get("runtime", {})
        if ready.get("runtime", {}).get("state") != "running":
            receipt["state"] = "blocked"
            receipt["reason"] = "runtime_not_ready"
            return 2
        runtime_receipt = _json((data / "runtime.json").read_text(encoding="utf-8"))
        port = int(runtime_receipt.get("port", port))
        token_path = data / "runtime-token"
        if token_path.exists():
            token = token_path.read_text(encoding="utf-8").strip()
        if not _wait_for_http(port, token):
            receipt["state"] = "blocked"
            receipt["reason"] = "recall_http_not_ready"
            receipt["port"] = port
            return 2

        cli_latencies: list[float] = []
        http_latencies: list[float] = []
        errors: list[str] = []
        for _ in range(args.samples):
            started = time.perf_counter()
            result = _run(
                cli,
                [
                    "recall",
                    "budget decision",
                    "--limit",
                    "8",
                    "--json",
                ],
                env,
            )
            cli_latencies.append(time.perf_counter() - started)
            if result.returncode != 0:
                errors.append(f"cli:{result.returncode}:{result.stderr.strip()[:200]}")
            try:
                http_latencies.append(_http_recall(port, token, "budget decision"))
            except RuntimeError as error:
                errors.append(str(error))
            time.sleep(args.interval)

        receipt["cli_recall"] = _stats(cli_latencies)
        receipt["http_recall"] = _stats(http_latencies)
        receipt["errors"] = errors
        receipt["state"] = "passed" if not errors else "failed"
        return 0 if receipt["state"] == "passed" else 1
    finally:
        _run(cli, ["stop"], env)
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                process.kill()
        shutil.rmtree(work, ignore_errors=True)
        receipt["cleaned"] = not work.exists()
        print(json.dumps(receipt, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    raise SystemExit(main())
