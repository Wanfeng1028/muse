import asyncio
import hashlib
import json
import logging
from collections.abc import Callable
from typing import Any, cast

import httpx

from one_memory.database_access import main_database
from one_memory.http_client import create_async_client
from one_memory.memory_server.migrations import matter_model_cache_ddl
from one_memory.model_profiles import (
    ModelProfile,
    ModelProfileStore,
    ProviderKind,
    attach_disable_thinking,
)
from one_memory.secrets import SecretStore


class MatterModel:
    def __init__(
        self,
        profiles: ModelProfileStore,
        secrets: SecretStore,
        *,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self.profiles = profiles
        self.secrets = secrets
        self.transport = transport
        self.evidence_guard: Callable[[], None] | None = None
        with main_database(profiles.database_path).write() as db, db:
            # Schema owned by `memory_server.migrations` (migration 24).
            db.execute(matter_model_cache_ddl("sqlite"))

    def profile(self, profile_id: str | None = None) -> ModelProfile:
        profile = (
            self.profiles.require(profile_id, self.secrets)
            if profile_id
            else self.profiles.active(self.secrets)
        )
        if profile is None:
            raise ValueError("matter_model_not_configured")
        if profile.provider_kind not in {ProviderKind.OPENAI_COMPATIBLE, ProviderKind.OLLAMA}:
            raise ValueError("matter_model_provider_not_supported")
        return profile

    async def complete(
        self, system: str, data: dict[str, Any], *, profile_id: str | None = None
    ) -> dict[str, Any]:
        if self.evidence_guard is not None:
            self.evidence_guard()
        profile = self.profile(profile_id)
        cache_key = hashlib.sha256(
            json.dumps(
                {
                    "request_policy": "matter-json-v3",
                    "profile": profile.profile_id,
                    "revision": profile.revision,
                    "system": system,
                    "data": data,
                },
                sort_keys=True,
            ).encode()
        ).hexdigest()
        with main_database(self.profiles.database_path).read() as db:
            cached = db.execute(
                "SELECT body FROM matter_model_cache WHERE cache_key=?", (cache_key,)
            ).fetchone()
        if cached:
            return cast(dict[str, Any], json.loads(cached[0]))
        reference = self.profiles.secret_ref(profile.profile_id)
        secret = self.secrets.resolve(reference) if reference else None
        messages = [
            {"role": "system", "content": system},
            {"role": "user", "content": json.dumps(data, ensure_ascii=False)},
        ]
        headers = {"Content-Type": "application/json"}
        if not profile.base_url:
            raise ValueError("matter_model_endpoint_unavailable")
        payload: dict[str, object]
        if profile.provider_kind is ProviderKind.OLLAMA:
            url = profile.base_url.rstrip("/") + "/api/chat"
            payload = {
                "model": profile.model,
                "messages": messages,
                "stream": False,
                "format": "json",
                "options": {
                    "temperature": 0,
                    "num_predict": 12000,
                    "num_ctx": profile.context_window or 32768,
                },
            }
        else:
            if not secret:
                raise ValueError("matter_model_secret_unavailable")
            url = profile.base_url.rstrip("/") + "/chat/completions"
            headers["Authorization"] = f"Bearer {secret}"
            payload = {
                "model": profile.model,
                "messages": messages,
                "stream": False,
                "temperature": 0,
                "max_tokens": 16000,
            }
        attach_disable_thinking(profile, payload)
        if profile.disable_thinking and profile.model.startswith("deepseek-"):
            payload["thinking"] = {"type": "disabled"}
        elif profile.model.startswith("deepseek-"):
            payload["thinking"] = {"type": "enabled"}
            payload["reasoning_effort"] = "low"
            payload["max_tokens"] = 32768
        try:
            async with create_async_client(
                timeout=profile.timeout_seconds, follow_redirects=False, transport=self.transport
            ) as client:
                for format_attempt in range(2):
                    response = await self._post(client, url, headers, payload)
                    if self.evidence_guard is not None:
                        self.evidence_guard()
                    try:
                        parsed = self._json_response(response, profile.provider_kind)
                        break
                    except json.JSONDecodeError:
                        if format_attempt:
                            raise
                        payload = {
                            **payload,
                            "messages": [
                                *messages,
                                {
                                    "role": "user",
                                    "content": "上次回复不是有效的 JSON 对象。"
                                    "请只返回符合原要求的 JSON 对象，"
                                    "不要Markdown或解释。原始资料和字段要求保持不变，不添加事实。",
                                },
                            ],
                        }
            with main_database(self.profiles.database_path).write() as db, db:
                db.execute(
                    "INSERT OR REPLACE INTO matter_model_cache VALUES (?,?)",
                    (cache_key, json.dumps(parsed)),
                )
            return parsed
        except json.JSONDecodeError as error:
            raise ValueError("matter_model_invalid_json") from error
        except (KeyError, IndexError, AttributeError, TypeError) as error:
            raise ValueError("matter_model_response_invalid") from error

    @staticmethod
    def _json_response(response: httpx.Response, provider: ProviderKind) -> dict[str, Any]:
        if response.status_code != 200:
            try:
                error = response.json().get("error", {})
            except (ValueError, AttributeError):
                error = {}
            if isinstance(error, dict) and (
                error.get("type") == "UserBudgetExhausted" or str(error.get("code")) == "2005"
            ):
                raise ValueError("matter_model_budget_exhausted")
            raise ValueError(f"matter_model_http_{response.status_code}")
        envelope = response.json()
        if provider is ProviderKind.OLLAMA:
            text = envelope["message"]["content"]
        else:
            choice = envelope["choices"][0]
            if choice.get("finish_reason") == "length":
                raise ValueError("matter_model_output_truncated")
            text = choice["message"]["content"]
        text = text.strip()
        if text.startswith("```json\n") and text.endswith("```"):
            text = text[8:-3].strip()
        parsed = json.loads(text)
        if not isinstance(parsed, dict):
            raise json.JSONDecodeError("Expected an object", text, 0)
        return cast(dict[str, Any], parsed)

    async def _post(
        self,
        client: httpx.AsyncClient,
        url: str,
        headers: dict[str, str],
        payload: dict[str, object],
    ) -> httpx.Response:
        for attempt in range(2):
            if self.evidence_guard is not None:
                self.evidence_guard()
            try:
                response = await client.post(url, headers=headers, json=payload)
            except httpx.TransportError as error:
                if attempt:
                    code = (
                        "matter_model_timeout"
                        if isinstance(error, httpx.TimeoutException)
                        else "matter_model_transport_failed"
                    )
                    raise ValueError(code) from error
                reason = type(error).__name__
            else:
                if response.status_code not in {429, 502, 503, 504} or attempt:
                    return response
                reason = f"http_{response.status_code}"
            logging.getLogger(__name__).warning("matter_model_retry: %s", reason)
            await asyncio.sleep(0.25)
        raise AssertionError("unreachable")
