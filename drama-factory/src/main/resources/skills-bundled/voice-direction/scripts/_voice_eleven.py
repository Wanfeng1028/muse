"""ElevenLabs HTTP helpers shared by vo_record.py and voice_qa.py: env file, key, retries with backoff, usage headers."""
import os
import random
import sys
import time
from dataclasses import dataclass
from pathlib import Path

import httpx

API_ROOT = "https://api.elevenlabs.io/v1"
MAX_TRIES = 4
RETRY_STATUSES = {429, 500, 502, 503, 504}


def load_env_file(path: Path | None) -> None:
    if not path:
        return
    if not path.is_file():
        sys.exit(f"error: --env-file {path} not found")
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_key(name: str = "ELEVENLABS_API_KEY") -> str:
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: {name} is not set (export it or pass --env-file)")
    return value


@dataclass
class Reply:
    status: int
    headers: dict[str, str]
    content: bytes
    tries: int
    error: str = ""

    @property
    def ok(self) -> bool:
        return self.status == 200

    def json(self) -> dict:
        return httpx.Response(self.status, content=self.content).json()

    def usage(self) -> dict[str, str | float | None]:
        cost = self.headers.get("character-cost") or self.headers.get("x-character-count")
        return {
            "request_id": self.headers.get("request-id") or self.headers.get("x-request-id"),
            "character_cost": float(cost) if cost else None,
            "concurrent_requests": self.headers.get("current-concurrent-requests"),
            "max_concurrent_requests": self.headers.get("maximum-concurrent-requests"),
        }


def _wait_seconds(attempt: int, response: httpx.Response | None) -> float:
    retry_after = response.headers.get("retry-after") if response is not None else None
    if retry_after and retry_after.replace(".", "", 1).isdigit():
        return min(60.0, float(retry_after))
    return 2.0 * 2 ** (attempt - 1) + random.uniform(0, 0.5)


def send(method: str, url: str, key: str, log_prefix: str = "", **kwargs: object) -> Reply:
    """Request with up to 4 tries; retries 429/5xx and network errors with exponential backoff (2, 4, 8 s)."""
    response: httpx.Response | None = None
    for attempt in range(1, MAX_TRIES + 1):
        try:
            response = httpx.request(method, url, headers={"xi-api-key": key}, timeout=180, **kwargs)  # type: ignore[arg-type]
        except httpx.HTTPError as error:
            if attempt == MAX_TRIES:
                return Reply(0, {}, b"", attempt, f"{type(error).__name__}: {error}")
            response = None
        else:
            if response.status_code not in RETRY_STATUSES or attempt == MAX_TRIES:
                headers = {name.lower(): value for name, value in response.headers.items()}
                return Reply(response.status_code, headers, response.content, attempt, "" if response.status_code == 200 else response.text[:300])
            live = response.headers.get("current-concurrent-requests")
            print(f"{log_prefix}HTTP {response.status_code}, retrying" + (f" (concurrent requests: {live})" if live else ""), flush=True)
        time.sleep(_wait_seconds(attempt, response))
    return Reply(0, {}, b"", MAX_TRIES, "unreachable")
