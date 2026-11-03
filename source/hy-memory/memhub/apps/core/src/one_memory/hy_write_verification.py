"""Input checks around HY's native extractor; HY's output is published as it returns it."""

import asyncio
from typing import Any

from one_memory.hy_source_context import HyWriteBindings


def _extracted_items(info: dict[str, Any]) -> list[dict[str, Any]]:
    items: list[dict[str, Any]] = []
    for section in ("memory", "intentions"):
        for item in info.get(section) or []:
            if isinstance(item, dict) and isinstance(item.get("content"), str):
                items.append({"content": item["content"], "owner": item.get("owner")})
    for name, value in (info.get("basic_info") or {}).items():
        items.append({"content": f"{name}: {value}", "owner": "user"})
    return items


class HyExtractionGuard:
    def __init__(self, extractor: Any) -> None:
        self.extractor = extractor
        self.failures: list[str] = []
        self._lock = asyncio.Lock()
        self.bindings: HyWriteBindings | None = None

    def __getattr__(self, name: str) -> Any:
        return getattr(self.extractor, name)

    async def extract(self, *args: Any, **kwargs: Any) -> Any:
        async with self._lock:
            try:
                return await self._extract(args, kwargs)
            except ValueError as error:
                if str(error).startswith("hy_memory_write_verification"):
                    self.failures.append(str(error))
                raise

    async def _extract(self, args: tuple[Any, ...], kwargs: dict[str, Any]) -> Any:
        content = kwargs.get("content", args[0] if args else "")
        bindings = self.bindings
        if bindings is not None:
            bindings.check_content(content)
            fields = kwargs.get("basic_profile_fields")
            bindings.profile_order = list(fields) if fields else None
            kwargs = {**kwargs, "history_context": bindings.history_json()}
        else:
            # No raw-history identity was supplied; do not trust HY's text prefixes.
            kwargs = {**kwargs, "history_context": ""}
        result = await self.extractor.extract(*args, **kwargs)
        if bindings is not None and result.success:
            bindings.record_turn_supports(_extracted_items(result.info))
        return result
