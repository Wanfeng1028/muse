"""Shared plumbing for gen_image.py: env keys, HTTP retries, error parsing, rate limiting and the cost meter."""
import collections
import json
import os
import sys
import threading
import time
from pathlib import Path

import httpx

sys.dont_write_bytecode = True

TIMEOUT = 600
MAX_RETRIES = 3
NEVER_RETRY = {"image_generation_user_error", "moderation_blocked", "invalid_request_error"}
KEY_NAMES = {"openai": "OPENAI_API_KEY", "gemini": "GEMINI_API_KEY", "bfl": "BFL_API_KEY", "recraft": "RECRAFT_API_KEY"}


class ApiError(Exception):
    pass


def load_env_file(path: Path | None) -> None:
    if not path:
        return
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.removeprefix("export ").split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def require_key(provider: str) -> str:
    name = KEY_NAMES[provider]
    value = os.environ.get(name)
    if not value:
        sys.exit(f"error: {name} is not set (export it or pass --env-file)")
    return value


def error_summary(response: httpx.Response) -> tuple[str, bool]:
    retryable = response.status_code == 429 or response.status_code >= 500
    try:
        body = response.json()
    except ValueError:
        return f"HTTP {response.status_code} non-JSON body: {response.text[:300]!r}", retryable
    error = body.get("error") if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return f"HTTP {response.status_code} {json.dumps(body)[:400]}", retryable
    kind, code = error.get("type"), error.get("code")
    message = f"HTTP {response.status_code} type={kind} code={code}: {error.get('message', '')[:300]}"
    details = error.get("moderation_details") or body.get("moderation_details")
    if details:
        message += f"  moderation_details={json.dumps(details)} (rephrase; never resend unchanged)"
    if kind in NEVER_RETRY or code in NEVER_RETRY:
        retryable = False
    return message, retryable


def retry_delay(response: httpx.Response | None, attempt: int) -> float:
    header = response.headers.get("retry-after") if response is not None else None
    if header and header.replace(".", "", 1).isdigit():
        return min(float(header), 60.0)
    return 2.0 * (2 ** attempt)


def request_with_retries(method: str, url: str, **kwargs: object) -> httpx.Response:
    for attempt in range(MAX_RETRIES + 1):
        try:
            response = httpx.request(method, url, timeout=TIMEOUT, **kwargs)
        except httpx.TransportError as error:
            if attempt == MAX_RETRIES:
                raise ApiError(f"network error after {MAX_RETRIES} retries: {error}") from error
            time.sleep(retry_delay(None, attempt))
            continue
        if response.status_code < 400:
            return response
        message, retryable = error_summary(response)
        if not retryable or attempt == MAX_RETRIES:
            raise ApiError(message)
        delay = retry_delay(response, attempt)
        print(f"  retry {attempt + 1}/{MAX_RETRIES} in {delay:.0f}s: {message[:120]}", flush=True)
        time.sleep(delay)
    raise ApiError("unreachable")


def json_body(response: httpx.Response) -> dict:
    if "json" not in response.headers.get("content-type", "") or len(response.content) < 2:
        raise ApiError(f"expected JSON, got {response.headers.get('content-type')} ({len(response.content)} bytes)")
    return response.json()


class RateLimiter:
    def __init__(self, images_per_minute: int) -> None:
        self.limit = max(1, images_per_minute)
        self.starts: collections.deque[tuple[float, int]] = collections.deque()
        self.lock = threading.Lock()

    def acquire(self, images: int) -> None:
        images = min(images, self.limit)
        while True:
            with self.lock:
                now = time.monotonic()
                while self.starts and now - self.starts[0][0] >= 60:
                    self.starts.popleft()
                if sum(count for _, count in self.starts) + images <= self.limit:
                    self.starts.append((now, images))
                    return
                wait = 60 - (now - self.starts[0][0])
            time.sleep(max(0.2, wait))


class CostMeter:
    def __init__(self, budget: float | None) -> None:
        self.budget = budget
        self.spent = 0.0
        self.unknown = 0
        self.lock = threading.Lock()

    def allows(self, next_estimate: float | None) -> bool:
        if self.budget is None:
            return True
        with self.lock:
            return self.spent + (next_estimate or 0.0) <= self.budget

    def add(self, cost: float | None) -> float:
        with self.lock:
            if cost is None:
                self.unknown += 1
            else:
                self.spent += cost
            return self.spent

    def summary(self) -> str:
        budget = f" of budget ${self.budget:.2f}" if self.budget is not None else ""
        unknown = f" (+{self.unknown} requests with unknown cost)" if self.unknown else ""
        return f"spent ${self.spent:.4f}{budget}{unknown}"
